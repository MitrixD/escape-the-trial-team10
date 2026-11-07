import json
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest

from schema_check import assert_valid
from verdict_agent import live, service
from verdict_agent.adapty_cli import AdaptyCLI, RateLimited
from verdict_agent.model import VerdictError
from verdict_agent.cli import main

ONBOARDING = Path(__file__).parent / "fixtures" / "live" / "995b124f-9075-440d-83bb-20dbdf7d7fbb"


def run(capsys, argv):
    code = main(argv)
    out = capsys.readouterr()
    return code, json.loads(out.out), out.err


def test_replay_prints_valid_verdict_and_exits_zero(capsys):
    code, out, err = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING)])
    assert code == 0
    assert_valid(out)
    assert "Traceback" not in err


def test_horizon_zero_is_json_error(capsys):
    code, out, err = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING), "--horizon", "0"])
    assert code == 1
    assert list(out) == ["error"]
    assert "Traceback" not in err


def test_horizon_flag_reaches_verdict(capsys):
    code, out, _ = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING), "--horizon", "60"])
    assert code == 0
    assert out["horizon_days"] == 60


def test_unknown_replay_dir_is_json_error(capsys, tmp_path):
    code, out, err = run(capsys, ["some-id", "--replay", str(tmp_path / "missing")])
    assert code == 1
    assert list(out) == ["error"]
    assert "Traceback" not in err


def test_usage_error_is_json(capsys):
    code, out, _ = run(capsys, [])
    assert code == 1 and "error" in out


def test_unexpected_error_hides_details(monkeypatch, capsys):
    def boom(**kw):
        raise FileNotFoundError("/secret/path/.env")

    monkeypatch.setattr(service, "verdict", boom)
    code, out, err = run(capsys, ["x"])
    assert code == 1
    assert out == {"error": "unexpected FileNotFoundError"}
    assert "/secret/path/.env" in err
    assert err.count("\n") == 1


def test_rate_limit_error_is_public(monkeypatch):
    def limited(**kw):
        raise RateLimited(30)

    monkeypatch.setattr(service, "verdict", limited)
    assert service.safe_verdict(ab_test_id="x") == {"error": str(RateLimited(30))}


def test_service_passes_replay_as_path(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "run_live", lambda *a, **kw: seen.update(args=a, kw=kw) or {})
    service.verdict("abc", horizon=7, replay="/tmp/x")
    assert seen["args"] == ("abc",)
    assert seen["kw"] == {"horizon": 7, "replay": Path("/tmp/x"), "app_id": None, "today": None}


def test_unknown_test_error_names_the_id(capsys, tmp_path):
    for name in ("auth_whoami.json", "products_list.json", "as_of.json"):
        (tmp_path / name).write_text((ONBOARDING / name).read_text())
    code, out, _ = run(capsys, ["no-such-test-id", "--replay", str(tmp_path)])
    assert code == 1
    assert list(out) == ["error"]
    assert "no-such-test-id" in out["error"]


README_ARGV = [ONBOARDING.name, "--replay", "tests/fixtures/live/995b124f-9075-440d-83bb-20dbdf7d7fbb"]
REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = Path(__file__).parent / "fixtures" / "replay_onboarding.json"


def frozen_clock(monkeypatch, day):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(day.year, day.month, day.day, 12, tzinfo=tz)

    monkeypatch.setattr(live, "datetime", Clock)


def test_readme_replay_command_ignores_the_wall_clock(capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    outputs = []
    for day in (date(2026, 11, 8), date(2027, 3, 1)):
        frozen_clock(monkeypatch, day)
        code, out, _ = run(capsys, README_ARGV)
        assert code == 0, out
        outputs.append(json.dumps(out, sort_keys=True))
    assert outputs[0] == outputs[1]


def test_readme_replay_command_matches_the_snapshot(capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    code, out, _ = run(capsys, README_ARGV)
    assert code == 0
    assert_valid(out)
    assert out == json.loads(SNAPSHOT.read_text())


def test_as_of_flag_overrides_the_bundle_date(capsys):
    _, default, _ = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING)])
    code, later, _ = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING), "--as-of", "2026-11-20"])
    assert code == 0
    assert_valid(later)
    assert later != default


def test_bad_as_of_is_json_error(capsys):
    code, out, _ = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING), "--as-of", "20 Nov"])
    assert code == 1 and list(out) == ["error"]


def test_replay_without_as_of_file_is_clear_error(capsys, tmp_path):
    bundle = tmp_path / "bundle"
    shutil.copytree(ONBOARDING, bundle)
    (bundle / "as_of.json").unlink()
    code, out, _ = run(capsys, [ONBOARDING.name, "--replay", str(bundle)])
    assert code == 1
    assert "as_of.json" in out["error"] and "--as-of" in out["error"]


def test_replay_never_reads_env(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("ADAPTY_APP_ID", "FAKE-APP-VALUE")
    monkeypatch.setenv("ADAPTY_EXPECTED_COMPANY", "FAKE-COMPANY-VALUE")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ADAPTY_APP_ID=FAKE-APP-VALUE\n")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in ("auth_whoami.json", "products_list.json", "as_of.json"):
        (bundle / name).write_text((ONBOARDING / name).read_text())
    code, out, err = run(capsys, ["no-such-test-id", "--replay", str(bundle)])
    assert code == 1
    assert "FAKE-APP-VALUE" not in json.dumps(out) + err
    assert "FAKE-COMPANY-VALUE" not in json.dumps(out) + err
    code, out, err = run(capsys, [ONBOARDING.name, "--replay", str(ONBOARDING)])
    assert code == 0 and "FAKE-APP-VALUE" not in json.dumps(out) + err


class LiveRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        args = cmd[1:]
        self.calls.append(args)
        if args[:2] == ["auth", "whoami"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"company": "Synthetic Co"}), "")
        if args[:2] == ["products", "list"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"data": []}), "")
        return subprocess.CompletedProcess(cmd, 1, "", "test not found in app CALL-APP-77")


@pytest.fixture
def live_runner(monkeypatch, tmp_path):
    runner = LiveRunner()
    monkeypatch.setattr(live, "AdaptyCLI", lambda **kw: AdaptyCLI(runner=runner, min_interval=0))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(live, "REPO_ENV", tmp_path / "missing.env")
    monkeypatch.setenv("ADAPTY_EXPECTED_COMPANY", "Synthetic Co")
    monkeypatch.setenv("ADAPTY_APP_ID", "ENV-APP-11")
    return runner


def test_app_flag_reaches_the_wrapper_and_is_never_echoed(capsys, live_runner):
    code, out, _ = run(capsys, ["t-404", "--app", "CALL-APP-77"])
    assert code == 1
    data_calls = [c for c in live_runner.calls if c[:2] != ["auth", "whoami"]]
    assert data_calls and all(c[c.index("--app") + 1] == "CALL-APP-77" for c in data_calls)
    assert "cannot read A/B test t-404" in out["error"]
    assert "CALL-APP-77" not in out["error"] and "ENV-APP-11" not in out["error"]


def test_env_app_id_used_without_the_flag(capsys, live_runner):
    run(capsys, ["t-404"])
    assert all(c[c.index("--app") + 1] == "ENV-APP-11" for c in live_runner.calls if "--app" in c)


@pytest.mark.parametrize("exc, public", [
    (VerdictError("horizon must be at least 1 day"), "horizon must be at least 1 day"),
    (ValueError("detail with /secret/value"), "unexpected ValueError"),
    (json.JSONDecodeError("bad /secret/value", "doc", 0), "unexpected JSONDecodeError"),
    (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "/secret/value"), "unexpected UnicodeDecodeError"),
])
def test_only_our_own_value_errors_are_public(monkeypatch, exc, public):
    def fail(**kw):
        raise exc

    monkeypatch.setattr(service, "verdict", fail)
    assert service.safe_verdict(ab_test_id="x") == {"error": public}

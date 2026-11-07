import functools
import json
import subprocess

import pytest

import verdict_agent.live as live
import verdict_agent.service as service
from tests.live_fakes import APP, COMPANY, ONB_ID, FakeRunner
from verdict_agent.adapty_cli import AdaptyCLI
from verdict_agent.cli import main

SETTINGS = "Settings: upgrade vs lifetime anchor"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


class UnknownTestRunner(FakeRunner):
    def __call__(self, cmd, capture_output=True, text=True, **kwargs):
        if cmd[1:3] == ["ab-tests", "get"] and UNKNOWN_ID in cmd:
            self.calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 1, "", "A/B test not found")
        return super().__call__(cmd, capture_output, text, **kwargs)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    def make(dataset="/nowhere"):
        path = tmp_path / ".env"
        path.write_text(f"LUMEN_APP_ID={APP}\nADAPTY_EXPECTED_COMPANY={COMPANY}\nVERDICT_DATASET={dataset}\n")
        monkeypatch.setattr(service, "ENV_PATH", path)
        return path
    return make


@pytest.fixture
def fake_adapty(monkeypatch):
    runner = UnknownTestRunner()
    cli = AdaptyCLI(runner=runner, clock=lambda: 0.0, sleep=lambda s: None, min_interval=0)
    monkeypatch.setattr(live, "AdaptyCLI", lambda: cli)
    return runner


def run(capsys, argv):
    code = main(argv)
    out = capsys.readouterr()
    return code, json.loads(out.out), out.err


@pytest.mark.dataset
def test_offline_settings_prints_verdict(capsys, env_file, dataset_path):
    env_file(dataset_path)
    code, out, err = run(capsys, ["offline", SETTINGS, "--day", "14", "--traffic", "100"])
    assert code == 0
    assert out["verdict"] in {"not_enough_data", "early", "confirmed", "tie"}
    assert out["source"] == "offline" and out["horizon_source"] == "goal"
    assert "Traceback" not in err


@pytest.mark.dataset
def test_offline_horizon_flag(capsys, env_file, dataset_path):
    env_file(dataset_path)
    code, out, _ = run(capsys, ["offline", SETTINGS, "--horizon", "90"])
    assert code == 0
    assert out["horizon_days"] == 90 and out["horizon_source"] == "parameter"


def test_unknown_live_id_prints_error(capsys, env_file, fake_adapty):
    env_file()
    code, out, err = run(capsys, ["live", UNKNOWN_ID])
    assert code == 1
    assert set(out) == {"error"} and UNKNOWN_ID in out["error"]
    assert "Traceback" not in err


def test_horizon_out_of_range_errors_before_adapty(capsys, env_file, fake_adapty):
    env_file()
    code, out, _ = run(capsys, ["live", ONB_ID, "--horizon", "365"])
    assert code == 1
    assert out == {"error": "horizon must be between 1 and 120 days"}
    assert fake_adapty.calls == []


def test_wrong_account_prints_error(capsys, tmp_path, monkeypatch, fake_adapty):
    path = tmp_path / ".env"
    path.write_text(f"LUMEN_APP_ID={APP}\nADAPTY_EXPECTED_COMPANY=Another Company\nVERDICT_DATASET=/nowhere\n")
    monkeypatch.setattr(service, "ENV_PATH", path)
    code, out, _ = run(capsys, ["live", ONB_ID])
    assert code == 1 and "Another Company" in out["error"]


def test_unknown_offline_test_prints_error(capsys, env_file, monkeypatch):
    env_file()
    monkeypatch.setattr(service, "run_offline", functools.partial(_raise, ValueError("unknown offline test 'x'")))
    code, out, _ = run(capsys, ["offline", "x"])
    assert code == 1 and out == {"error": "unknown offline test 'x'"}


def _raise(exc, *args, **kwargs):
    raise exc


def test_service_needs_exactly_one_source():
    with pytest.raises(ValueError):
        service.verdict()
    with pytest.raises(ValueError):
        service.verdict(ab_test_id=ONB_ID, offline_test=SETTINGS)

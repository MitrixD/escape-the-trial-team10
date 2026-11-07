import json
from pathlib import Path

import pytest

from schema_check import assert_valid
from verdict_agent import service
from verdict_agent.adapty_cli import RateLimited
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
    assert seen["kw"] == {"horizon": 7, "replay": Path("/tmp/x")}


def test_unknown_test_error_names_the_id(capsys, tmp_path):
    for name in ("auth_whoami.json", "products_list.json"):
        (tmp_path / name).write_text((ONBOARDING / name).read_text())
    code, out, _ = run(capsys, ["no-such-test-id", "--replay", str(tmp_path)])
    assert code == 1
    assert list(out) == ["error"]
    assert "no-such-test-id" in out["error"]

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from verdict_agent import live
from verdict_agent.adapty_cli import AdaptyCLI, CliError, WrongAccount
from verdict_agent.model import VerdictError
from verdict_agent.live import run_live
from schema_check import assert_valid

LIVE = Path(__file__).parent / "fixtures" / "live"
ONBOARDING = LIVE / "995b124f-9075-440d-83bb-20dbdf7d7fbb"
TODAY = date(2026, 11, 8)


class CountingRunner:
    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd[1:])
        return self.inner(cmd, **kw)


@pytest.fixture
def counted(monkeypatch):
    holder = {}
    real = live.replay_runner

    def wrapped(directory):
        holder["runner"] = CountingRunner(real(directory))
        return holder["runner"]

    monkeypatch.setattr(live, "replay_runner", wrapped)
    return holder


def copy_bundle(src, tmp_path):
    dst = tmp_path / "bundle"
    shutil.copytree(src, dst)
    return dst


def test_replay_end_to_end_validates_within_call_budget(counted):
    out = run_live(ONBOARDING.name, today=TODAY, replay=ONBOARDING)
    assert_valid(out)
    assert 0 < len(counted["runner"].calls) <= 10


def few_events_bundle(tmp_path):
    bundle = copy_bundle(ONBOARDING, tmp_path)
    path = bundle / "ab-tests_metrics_total.json"
    metrics = json.loads(path.read_text())
    for row in metrics["data"]["metrics"]:
        row.update(users=40, purchases=1, trials=1, trials_paid=0, unique_paid_subscribers=1, revenue=49.99)
    path.write_text(json.dumps(metrics))
    for funnel in bundle.glob("analytics_funnel_*.json"):
        segments = [{"key": "lumen_monthly", "title": "lumen_monthly", "is_total": False,
                     "values": [{"x": 0, "title": "Paid", "value": 2}]},
                    {"key": "lumen_weekly", "title": "lumen_weekly", "is_total": False,
                     "values": [{"x": 0, "title": "Trial", "value": 3}, {"x": 1, "title": "1 period", "value": 0}]}]
        funnel.write_text(json.dumps({"data": {"segments": segments}}))
    return bundle


def test_replay_with_few_events_is_not_enough_data_with_a_come_back_date(counted, tmp_path):
    out = run_live(ONBOARDING.name, today=TODAY, replay=few_events_bundle(tmp_path))
    assert_valid(out)
    assert (out["verdict"], out["reason"]) == ("not_enough_data", "min_events")
    assert out["come_back_on"] is not None
    assert [a["users"] for a in out["arms"]] == [40, 40]
    assert 0 < len(counted["runner"].calls) <= 10


def test_horizon_error_before_any_call(counted, tmp_path):
    with pytest.raises(ValueError):
        run_live(ONBOARDING.name, today=TODAY, horizon=0, replay=ONBOARDING, env_path=tmp_path / "missing.env")
    assert "runner" not in counted


def test_wrong_account_stops_before_data_reads(counted, tmp_path):
    bundle = copy_bundle(ONBOARDING, tmp_path)
    (bundle / "auth_whoami.json").write_text(json.dumps({"company": "x", "matched_expected_company": False}))
    with pytest.raises(WrongAccount):
        run_live(ONBOARDING.name, today=TODAY, replay=bundle)
    assert counted["runner"].calls == [["auth", "whoami", "--json"]]


def test_more_than_three_arms_rejected_before_funnel_calls(counted, tmp_path):
    bundle = copy_bundle(ONBOARDING, tmp_path)
    path = bundle / "ab-tests_get.json"
    test = json.loads(path.read_text())
    test["flows"] = test["flows"] * 2
    path.write_text(json.dumps(test))
    with pytest.raises(ValueError, match="more than 3 arms"):
        run_live(ONBOARDING.name, today=TODAY, replay=bundle)
    assert not any(c[:2] == ["analytics", "funnel"] for c in counted["runner"].calls)


def test_two_runs_give_identical_json():
    a = run_live(ONBOARDING.name, today=TODAY, replay=ONBOARDING)
    b = run_live(ONBOARDING.name, today=TODAY, replay=ONBOARDING)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_env_file_is_parsed_and_values_never_leak_in_errors(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# c\nADAPTY_APP_ID="app-secret-123"\nADAPTY_EXPECTED_COMPANY=\'me@example.com\'\n')
    assert live.read_env(env) == {"ADAPTY_APP_ID": "app-secret-123", "ADAPTY_EXPECTED_COMPANY": "me@example.com"}
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"company": "someone@else.test"}), "")

    monkeypatch.setattr(live, "AdaptyCLI", lambda **kw: AdaptyCLI(runner=runner, min_interval=0))
    monkeypatch.delenv("ADAPTY_APP_ID", raising=False)
    monkeypatch.delenv("ADAPTY_EXPECTED_COMPANY", raising=False)
    with pytest.raises(WrongAccount) as err:
        run_live(ONBOARDING.name, today=TODAY, env_path=env)
    assert "app-secret-123" not in str(err.value) and "me@example.com" not in str(err.value)


def test_replay_date_comes_from_the_bundle(tmp_path):
    assert json.loads((ONBOARDING / "as_of.json").read_text()) == {"as_of": "2026-11-07"}
    bundle = copy_bundle(ONBOARDING, tmp_path)
    (bundle / "as_of.json").write_text(json.dumps({"as_of": "2026-11-20"}))
    assert run_live(ONBOARDING.name, replay=bundle) == run_live(ONBOARDING.name, today=date(2026, 11, 20), replay=ONBOARDING)


def test_replay_without_as_of_and_today_raises(tmp_path):
    bundle = copy_bundle(ONBOARDING, tmp_path)
    (bundle / "as_of.json").unlink()
    with pytest.raises(VerdictError, match="as_of.json"):
        run_live(ONBOARDING.name, replay=bundle)


def test_two_arm_replay_needs_eight_calls_without_cohort(counted):
    run_live(ONBOARDING.name, replay=ONBOARDING)
    calls = counted["runner"].calls
    assert len(calls) == 8
    assert not any(c[:2] == ["analytics", "cohort"] for c in calls)


class AppSpy:
    def __init__(self):
        self.apps = []

    def __call__(self, cmd, **kw):
        if "--app" in cmd:
            self.apps.append(cmd[cmd.index("--app") + 1])
        body = {"matched_expected_company": True} if cmd[1:3] == ["auth", "whoami"] else {"data": []}
        return subprocess.CompletedProcess(cmd, 0 if cmd[1:3] != ["ab-tests", "get"] else 1, json.dumps(body), "")


@pytest.fixture
def app_spy(monkeypatch, tmp_path):
    spy = AppSpy()
    monkeypatch.setattr(live, "AdaptyCLI", lambda **kw: AdaptyCLI(runner=spy, min_interval=0))
    monkeypatch.setenv("ADAPTY_EXPECTED_COMPANY", "Synthetic Co")
    env = tmp_path / ".env"
    env.write_text("ADAPTY_APP_ID=FILE-APP\nADAPTY_EXPECTED_COMPANY=File Co\n")
    return spy, env


def test_environment_wins_over_env_file(app_spy, monkeypatch):
    spy, env = app_spy
    monkeypatch.setenv("ADAPTY_APP_ID", "ENV-APP")
    with pytest.raises(CliError):
        run_live("t1", today=TODAY, env_path=env)
    assert set(spy.apps) == {"ENV-APP"}


def test_call_app_id_wins_over_environment_and_file(app_spy, monkeypatch):
    spy, env = app_spy
    monkeypatch.setenv("ADAPTY_APP_ID", "ENV-APP")
    with pytest.raises(CliError) as err:
        run_live("t1", today=TODAY, env_path=env, app_id="CALL-APP")
    assert set(spy.apps) == {"CALL-APP"}
    assert "CALL-APP" not in err.value.public and "cannot read A/B test t1" in err.value.public


def test_env_file_used_when_environment_has_no_app(app_spy, monkeypatch):
    spy, env = app_spy
    monkeypatch.delenv("ADAPTY_APP_ID", raising=False)
    with pytest.raises(CliError):
        run_live("t1", today=TODAY, env_path=env)
    assert set(spy.apps) == {"FILE-APP"}


def test_no_app_id_anywhere_is_a_verdict_error(monkeypatch, tmp_path):
    monkeypatch.delenv("ADAPTY_APP_ID", raising=False)
    with pytest.raises(VerdictError, match="app id"):
        run_live("t1", today=TODAY, env_path=tmp_path / "missing.env")


def test_default_env_path_falls_back_to_the_repo_root(monkeypatch, tmp_path):
    assert live.REPO_ENV == Path(live.__file__).resolve().parent.parent / ".env"
    monkeypatch.chdir(tmp_path)
    assert live.default_env_path() == live.REPO_ENV
    (tmp_path / ".env").write_text("ADAPTY_APP_ID=x\n")
    assert live.default_env_path() == Path(".env")


def test_env_values_may_carry_inline_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text('ADAPTY_APP_ID=app-1  # my app\nADAPTY_EXPECTED_COMPANY="Acme # Ltd"  # quoted keeps the hash\n'
                   "X=a#b\n")
    assert live.read_env(env) == {"ADAPTY_APP_ID": "app-1", "ADAPTY_EXPECTED_COMPANY": "Acme # Ltd", "X": "a#b"}

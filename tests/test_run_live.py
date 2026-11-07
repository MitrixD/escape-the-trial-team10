import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from verdict_agent import live
from verdict_agent.adapty_cli import WrongAccount
from verdict_agent.live import run_live
from schema_check import assert_valid

LIVE = Path(__file__).parent / "fixtures" / "live"
ONBOARDING = LIVE / "995b124f-9075-440d-83bb-20dbdf7d7fbb"
MAIN = LIVE / "1023db3c-27fe-4591-9750-28305309b3ca"
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


@pytest.mark.parametrize("bundle", [ONBOARDING, MAIN], ids=["onboarding", "main"])
def test_replay_end_to_end_validates_within_call_budget(bundle, counted):
    out = run_live(bundle.name, today=TODAY, replay=bundle)
    assert_valid(out)
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


def test_env_file_is_parsed_and_values_never_leak_in_errors(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nADAPTY_APP_ID="app-secret-123"\nADAPTY_EXPECTED_COMPANY=\'me@example.com\'\n')
    assert live.read_env(env) == {"ADAPTY_APP_ID": "app-secret-123", "ADAPTY_EXPECTED_COMPANY": "me@example.com"}
    bundle = copy_bundle(ONBOARDING, tmp_path)
    (bundle / "auth_whoami.json").write_text(json.dumps({"matched_expected_company": False}))
    with pytest.raises(WrongAccount) as err:
        run_live(ONBOARDING.name, today=TODAY, replay=bundle, env_path=env)
    assert "app-secret-123" not in str(err.value) and "me@example.com" not in str(err.value)

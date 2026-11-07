import json
from pathlib import Path

import pytest

from tests.helpers import groups_from_sample, load_spike, spike_sample
from verdict_agent.offline import load_users, offline_test, run_offline, trial_days_from

SETTINGS = "Settings: upgrade vs lifetime anchor"
ONBOARDING = "Onboarding: annual trial vs weekly first"
MAIN = "Main: 3 plans vs lifetime anchor (NA)"
VERDICTS = {"not_enough_data", "early", "confirmed", "tie"}
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def users(dataset_path):
    return load_users(dataset_path, 60)


@pytest.mark.dataset
def test_load_users_matches_spike_shape(users, spike_users):
    assert list(users) == list(spike_users)
    uid = next(iter(users))
    for key in ("test", "arm", "ev", "subs"):
        assert users[uid][key] == spike_users[uid][key]
    assert set(users[uid]["attrs"]) == {"platform", "acquisition_channel", "onboarding_goal", "push_opt_in"}


@pytest.mark.dataset
def test_settings_two_arms_of_1400(users):
    test = offline_test(users, SETTINGS, 14, 100)
    assert len(test.arms) == 2
    assert [arm.users for arm in test.arms] == [1400, 1400]
    assert test.source == "offline"
    assert test.ab_test_id == SETTINGS
    assert (test.as_of - test.started_on).days == 14
    assert test.users_per_day == 200
    assert [len(test.segment_rows[arm.title]) for arm in test.arms] == [1400, 1400]
    for arm in test.arms:
        assert 0 <= arm.paid_users <= arm.users
        assert arm.revenue_received == pytest.approx(sum(g.n * g.received for g in arm.groups))


@pytest.mark.dataset
def test_groups_match_spike_sampling(users, spike_users):
    test = offline_test(users, SETTINGS, 14, 100)
    first = test.arms[0]
    spike = load_spike()
    pop = [u for u in spike_users.values() if u["test"] == SETTINGS and u["arm"] == first.title]
    expected = groups_from_sample(spike, *spike_sample(spike, pop, 100, 14))
    key = lambda g: (g.status, g.product, g.age_days)
    got = sorted(first.groups, key=key)
    want = sorted(expected, key=key)
    assert [(key(g), g.n) for g in got] == [(key(g), g.n) for g in want]
    for g, w in zip(got, want):
        assert g.received == pytest.approx(w.received)


@pytest.mark.dataset
def test_trial_days_from_data(users):
    days = trial_days_from(users)
    assert days and all(isinstance(v, int) and v > 0 for v in days.values())


@pytest.mark.dataset
@pytest.mark.parametrize("name,slug", [(ONBOARDING, "onboarding"), (SETTINGS, "settings"), (MAIN, "main")])
def test_run_offline_day14(dataset_path, name, slug):
    out = run_offline(dataset_path, name, 14, 100)
    assert out["source"] == "offline"
    assert out["verdict"] in VERDICTS
    assert out["ab_test_id"] == name
    if name == SETTINGS:
        assert out["segments_checked"] > 0
    (FIXTURES / f"offline_day14_{slug}.json").write_text(json.dumps(out, indent=2) + "\n")


@pytest.mark.dataset
def test_onboarding_weekly_refund_ok(dataset_path):
    out = run_offline(dataset_path, ONBOARDING, 14, 100)
    weekly = next(arm for arm in out["arms"] if arm["title"] == "onb_weekly")
    refund = next(w for w in weekly["warnings"] if w["metric"] == "refund_rate_per_payer")
    assert refund["status"] == "ok"


@pytest.mark.dataset
def test_unknown_test_names_available(dataset_path):
    with pytest.raises(ValueError, match="Settings: upgrade vs lifetime anchor"):
        run_offline(dataset_path, "No such test", 14, 100)

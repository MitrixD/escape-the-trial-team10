import math
from datetime import date, timedelta

import pytest

from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.model import Group
from verdict_agent.stats import users_needed
from verdict_agent.verdict import check_horizon
from tests.helpers import START, make_arm, make_cal, make_test, step_curve
from tests.helpers import build_checked_verdict as build_verdict


def two_arms(gain, users, payers_a, payers_b, **kw):
    cal = make_cal({"p": step_curve(gain)})
    test = make_test([make_arm("A", users, payers_a), make_arm("B", users, payers_b)], **kw)
    return test, cal


def pooled_sd(xa, xb):
    def ss(xs):
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs)
    return math.sqrt((ss(xa) + ss(xb)) / (len(xa) + len(xb) - 2))


def test_horizon_defaults_to_60():
    assert check_horizon(None) == 60
    assert check_horizon(30) == 30


@pytest.mark.parametrize("bad", [0, -5])
def test_horizon_below_one_is_rejected(bad):
    with pytest.raises(ValueError):
        check_horizon(bad)
    test, cal = two_arms(15.0, 200, 49, 66)
    with pytest.raises(ValueError):
        build_verdict(test, cal, horizon=bad)


def test_caller_horizon_is_used_for_expected_revenue():
    test, cal = two_arms(15.0, 200, 49, 66)
    out = build_verdict(test, cal, horizon=30)
    assert out["horizon_days"] == 30
    for arm, row in zip(test.arms, out["arms"]):
        assert row["revenue_expected_renewals"] == round(estimate(arm, cal, 30).from_renewals, 2)
    assert out["arms"][1]["revenue_expected_renewals"] != build_verdict(test, cal)["arms"][1]["revenue_expected_renewals"]


def test_goal_in_the_title_is_not_parsed_for_a_horizon():
    test, cal = two_arms(15.0, 200, 49, 66, title="Goal: best 90-day revenue")
    assert build_verdict(test, cal)["horizon_days"] == 60


def test_min_events_date_at_observed_rate():
    test, cal = two_arms(15.0, 200, 49, 66, days_running=3)
    test.arms[0].purchases = 12
    out = build_verdict(test, cal)
    assert out["reason"] == "min_events"
    assert out["come_back_on"] == (test.as_of + timedelta(days=5)).isoformat()


def test_min_events_date_is_null_without_any_event():
    test, cal = two_arms(15.0, 200, 49, 66)
    test.arms[0].purchases = 0
    assert build_verdict(test, cal)["come_back_on"] is None


def test_no_calibration_has_no_date():
    test, _ = two_arms(15.0, 200, 49, 66)
    out = build_verdict(test, make_cal({}, source="none"))
    assert out["reason"] == "no_calibration"
    assert out["come_back_on"] is None


def with_trials(trial_days, users_per_day=1e9):
    cal = make_cal({"p": step_curve(10.0), "q": step_curve(10.0)}, trial_days=trial_days)
    test, _ = two_arms(10.0, 200, 67, 72, started_on=date(2026, 11, 7), users_per_day=users_per_day)
    test.arms[0].groups.append(Group("trial", "p", 3, 10, 0.0))
    test.arms[1].groups.append(Group("trial", "q", 3, 10, 0.0))
    return test, cal


def test_pending_revenue_date_after_trials_and_first_renewal():
    test, cal = with_trials({"p": 7, "q": 7}, users_per_day=100.0)
    out = build_verdict(test, cal)
    assert out["reason"] == "pending_revenue"
    assert date(2026, 12, 14) <= date.fromisoformat(out["come_back_on"]) <= date(2026, 11, 7) + timedelta(days=60)


def test_pending_revenue_date_uses_longest_trial():
    test, cal = with_trials({"p": 7, "q": 14})
    out = build_verdict(test, cal)
    assert out["reason"] == "pending_revenue"
    assert out["come_back_on"] == "2026-12-21"


def test_unknown_trial_length_defaults_to_seven_days():
    test, cal = with_trials({})
    assert build_verdict(test, cal)["come_back_on"] == "2026-12-14"


def test_no_trial_groups_means_start_plus_renewal_period():
    test, cal = two_arms(10.0, 200, 67, 72, users_per_day=1e9)
    assert build_verdict(test, cal)["come_back_on"] == (START + timedelta(days=30)).isoformat()


def test_underpowered_date_from_sample_size():
    test, cal = two_arms(10 / 0.83 - 10, 200, 53, 62, days_running=40, users_per_day=200.0)
    out = build_verdict(test, cal)
    assert out["reason"] == "underpowered"
    xa, xb = pseudo_values(test.arms[0], cal, 60), pseudo_values(test.arms[1], cal, 60)
    delta = abs(sum(xb) / len(xb) - sum(xa) / len(xa))
    days = math.ceil((users_needed(delta, pooled_sd(xa, xb)) - 200) / 100.0)
    expected = test.as_of + timedelta(days=days)
    assert expected < START + timedelta(days=60)
    assert out["come_back_on"] == expected.isoformat()


def test_date_is_capped_at_horizon():
    test, cal = two_arms(10 / 0.83 - 10, 200, 53, 62, days_running=40, users_per_day=1.0)
    assert build_verdict(test, cal)["come_back_on"] == (START + timedelta(days=60)).isoformat()


def test_no_traffic_is_capped_at_horizon():
    test, cal = two_arms(10 / 0.83 - 10, 200, 53, 62, days_running=40, users_per_day=0.0)
    assert build_verdict(test, cal)["come_back_on"] == (START + timedelta(days=60)).isoformat()


def test_date_is_never_before_today():
    test, cal = two_arms(10 / 0.83 - 10, 200, 53, 62, days_running=70, users_per_day=1.0)
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    assert out["come_back_on"] == test.as_of.isoformat()


def test_no_date_when_confirmed():
    out = build_verdict(*two_arms(15.0, 200, 49, 66))
    assert out["verdict"] == "confirmed"
    assert out["come_back_on"] is None


def test_no_date_when_tie():
    out = build_verdict(*two_arms(10 / 0.9 - 10, 20000, 10000, 10000))
    assert out["verdict"] == "tie"
    assert out["come_back_on"] is None


def test_tiny_traffic_does_not_overflow_and_is_capped():
    test, cal = two_arms(10 / 0.83 - 10, 200, 53, 62, days_running=40, users_per_day=1e-12)
    assert build_verdict(test, cal)["come_back_on"] == (START + timedelta(days=60)).isoformat()

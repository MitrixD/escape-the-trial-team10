"""Change harden-verdict-agent, groups 3, 4.1 and 4.2: confidence, three arms, dates, calibration gaps."""
import math
from datetime import timedelta

import pytest

from verdict_agent import verdict as verdict_module
from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.stats import users_needed
from tests.helpers import make_arm, make_cal, make_test, step_curve
from tests.helpers import build_checked_verdict as build_verdict


def trial_vs_upfront():
    cal = make_cal({"up": [40.0] * 61, "tr": [0.0] * 31 + [60.0] * 30}, conv=0.3)
    a = make_arm("A", 400, 40, received=40.0, product="up", purchases=40)
    b = make_arm("B", 400, 120, received=0.0, status="trial", product="tr", purchases=0, trials=120)
    return make_test([a, b]), cal


def test_trial_outcome_spread_lowers_confidence():
    out = build_verdict(*trial_vs_upfront())
    assert out["leader"] == "B"
    assert out["p2bb_expected"] < 0.95
    assert out["verdict"] != "confirmed"


def test_pseudo_values_keep_the_exact_mean():
    test, cal = trial_vs_upfront()
    for arm in test.arms:
        values = pseudo_values(arm, cal, 60)
        assert len(values) == arm.users
        assert sum(values) / len(values) == pytest.approx(estimate(arm, cal, 60).total, abs=1e-9)


def test_three_arms_report_the_chance_to_be_best():
    cal = make_cal({"p": step_curve(15.0)})
    arms = [make_arm("A", 400, 100), make_arm("B", 400, 100), make_arm("C", 400, 112)]
    out = build_verdict(make_test(arms), cal)
    assert out["leader"] == "C"
    pairwise = verdict_module.p2bb(pseudo_values(arms[1], cal, 60), pseudo_values(arms[2], cal, 60))
    assert out["p2bb_expected"] < math.floor(pairwise * 1e4) / 1e4
    assert build_verdict(make_test(arms), cal)["p2bb_expected"] == out["p2bb_expected"]


def test_come_back_date_uses_the_lagging_arms_traffic():
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 900, 300), make_arm("B", 100, 36)], days_running=10, users_per_day=100.0)
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    leader = next(a for a in test.arms if a.title == out["leader"])
    other = next(a for a in test.arms if a.title != out["leader"])
    lv, ov = pseudo_values(leader, cal, 60), pseudo_values(other, cal, 60)
    delta = abs(sum(lv) / len(lv) - sum(ov) / len(ov))
    missing = users_needed(delta, verdict_module._pooled_sd(ov, lv)) - min(len(lv), len(ov))
    lagging = min(test.arms, key=lambda a: a.users)
    expected_days = math.ceil(missing / (lagging.users / 10))
    cap = test.started_on + timedelta(days=60)
    assert out["come_back_on"] == min(test.as_of + timedelta(days=expected_days), cap).isoformat()


def test_nothing_new_to_wait_for_before_the_horizon_is_not_the_horizon():
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 60), make_arm("B", 200, 60)], days_running=40)
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    assert out["next_action_basis"] != "horizon"
    assert out["come_back_on"] == (test.as_of + timedelta(days=7)).isoformat()


def test_horizon_reached_when_the_test_is_as_old_as_the_horizon():
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 60), make_arm("B", 200, 60)], days_running=60)
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    assert out["next_action_basis"] == "horizon"


def test_trials_without_any_conversion_rate_are_no_calibration():
    cal = make_cal({"up": [40.0] * 61, "tr": [0.0] * 31 + [60.0] * 30}, conv=None)
    a = make_arm("A", 400, 40, received=40.0, product="up", purchases=40)
    b = make_arm("B", 400, 120, received=0.0, status="trial", product="tr", purchases=0, trials=120)
    out = build_verdict(make_test([a, b]), cal)
    assert (out["verdict"], out["reason"]) == ("not_enough_data", "no_calibration")


def test_annual_product_gets_no_renewals_before_a_year():
    cal = make_cal({"y": [0.0] + [40.0] * 30 + [55.0] * 30})
    cal.periods = {"y": "annual"}
    assert cal.expected("active", "y", 3, 60) <= 0
    cal.periods = {"y": "weekly"}
    assert cal.expected("active", "y", 3, 60) > 0


def test_lifetime_product_gets_no_renewals():
    cal = make_cal({"l": [0.0] + [40.0] * 30 + [55.0] * 30})
    cal.periods = {"l": "lifetime"}
    assert cal.expected("active", "l", 3, 60) <= 0


@pytest.mark.parametrize("period, renews_by_day_60", [
    ("weekly", True), ("monthly", True), ("two_months", False), ("trimonthly", False),
    ("semiannual", False), ("annual", False), ("lifetime", False)])
def test_every_catalog_period_is_compared_with_the_horizon(period, renews_by_day_60):
    cal = make_cal({"p": [0.0] + [40.0] * 30 + [55.0] * 30})
    cal.periods = {"p": period}
    assert (cal.expected("active", "p", 3, 60) > 0) is renews_by_day_60


def test_a_stopped_test_is_not_told_to_wait_for_more_users():
    from datetime import timedelta
    from tests.helpers import make_arm, make_test
    from verdict_agent.verdict import build_verdict
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 67), make_arm("B", 200, 72)], days_running=20, users_per_day=10.0)
    running = build_verdict(test, cal)
    test.running_days, test.stopped = 10, True
    stopped = build_verdict(test, cal)
    assert running["verdict"] == stopped["verdict"] == "keep_running"
    assert stopped["come_back_on"] < running["come_back_on"]

import math

import pytest

from verdict_agent import verdict as verdict_module
from verdict_agent.estimator import ArmEstimate, estimate, pseudo_values
from verdict_agent.stats import diff_ci, p2bb
from tests.helpers import make_arm, make_cal, make_test, step_curve
from tests.helpers import build_checked_verdict as build_verdict


def floor4(p):
    return math.floor(p * 1e4) / 1e4


def two_arms(gain, users, payers_a, payers_b):
    cal = make_cal({"p": step_curve(gain)})
    test = make_test([make_arm("A", users, payers_a), make_arm("B", users, payers_b)])
    return test, cal


def test_too_little_data_gives_min_events():
    test, cal = two_arms(15.0, 200, 49, 66)
    test.arms[0].purchases = 12
    out = build_verdict(test, cal)
    assert out["verdict"] == "not_enough_data"
    assert out["reason"] == "min_events"


def test_missing_calibration_gives_no_calibration():
    test, _ = two_arms(15.0, 200, 49, 66)
    cal = make_cal({}, source="none")
    out = build_verdict(test, cal)
    assert out["verdict"] == "not_enough_data"
    assert out["reason"] == "no_calibration"


def test_confident_before_maturity_is_confirmed():
    out = build_verdict(*two_arms(15.0, 200, 49, 66))
    assert out["p2bb_expected"] == pytest.approx(0.97, abs=0.005)
    assert out["maturity"] == pytest.approx(0.40, abs=0.001)
    assert out["verdict"] == "confirmed"
    assert out["reason"] is None


def test_immature_and_unsure_keeps_running_for_pending_revenue():
    out = build_verdict(*two_arms(10.0, 200, 67, 72))
    assert out["p2bb_expected"] == pytest.approx(0.70, abs=0.005)
    assert out["maturity"] == pytest.approx(0.50, abs=0.001)
    assert out["verdict"] == "keep_running"
    assert out["reason"] == "pending_revenue"


def test_mature_unsure_and_underpowered_keeps_running():
    test, cal = two_arms(10 / 0.83 - 10, 200, 53, 62)
    out = build_verdict(test, cal)
    assert out["p2bb_expected"] == pytest.approx(0.84, abs=0.005)
    assert out["maturity"] == pytest.approx(0.83, abs=0.001)
    leader_value = 62 * (10 / 0.83) / 200
    assert out["verdict"] == "keep_running"
    assert out["reason"] == "underpowered"
    lo, hi = diff_ci(pseudo_values(test.arms[0], cal, 60), pseudo_values(test.arms[1], cal, 60))
    assert max(abs(lo), abs(hi)) > 0.05 * leader_value


def test_mature_and_provably_equal_is_tie():
    out = build_verdict(*two_arms(10 / 0.9 - 10, 20000, 10000, 10000))
    assert out["maturity"] == pytest.approx(0.90, abs=0.001)
    assert out["verdict"] == "tie"
    assert out["reason"] is None
    assert out["leader"] == "A"


def test_raw_and_expected_p2bb_disagreement_is_visible():
    cal = make_cal({"up": [10.0] * 61, "tr": [0.0] * 31 + [50.0] * 30})
    a = make_arm("A", 200, 40, received=10.0, product="up", purchases=40)
    b = make_arm("B", 200, 32, received=0.0, status="trial", product="tr", purchases=0, trials=32)
    out = build_verdict(make_test([a, b]), cal)
    assert out["leader"] == "B"
    assert out["p2bb_raw"] == 0.0
    assert out["p2bb_expected"] == 0.9976


def test_probability_just_under_threshold_is_floored_and_not_confirmed(monkeypatch):
    monkeypatch.setattr(verdict_module, "p2bb", lambda xa, xb: 0.949996)
    out = build_verdict(*two_arms(15.0, 200, 49, 66))
    assert out["p2bb_expected"] == 0.9499
    assert out["p2bb_raw"] == 0.9499
    assert out["verdict"] != "confirmed"


def test_single_arm_is_rejected():
    test, cal = two_arms(15.0, 200, 49, 66)
    test.arms = test.arms[:1]
    with pytest.raises(ValueError, match="an A/B test needs at least two arms"):
        build_verdict(test, cal)


def test_leader_is_compared_with_best_other_arm():
    cal = make_cal({"p": step_curve(15.0)})
    arms = [make_arm("A", 200, 40), make_arm("B", 200, 55), make_arm("C", 200, 66)]
    out = build_verdict(make_test(arms), cal)
    assert out["leader"] == "C"
    expected = p2bb(pseudo_values(arms[1], cal, 60), pseudo_values(arms[2], cal, 60))
    assert out["p2bb_expected"] == floor4(expected)


def test_maturity_is_one_without_any_revenue():
    cal = make_cal({"p": step_curve(15.0)})
    arms = [make_arm("A", 200, 0), make_arm("B", 200, 0)]
    out = build_verdict(make_test(arms), cal)
    assert out["maturity"] == 1.0
    assert out["leader"] == "A"


def test_output_has_exactly_the_contract_fields():
    out = build_verdict(*two_arms(15.0, 200, 49, 66))
    assert set(out) == {
        "ab_test_id", "verdict", "reason", "leader", "p2bb_expected", "p2bb_raw",
        "maturity", "horizon_days", "come_back_on", "arms", "calibration_source", "expected_gap_per_user",
    }
    assert out["calibration_source"] == "product"
    assert out["arms"][1] == {
        "title": "B",
        "users": 200,
        "revenue_received": round(66 * 10 / 200, 2),
        "revenue_expected_trials": 0.0,
        "revenue_expected_renewals": round(66 * 15 / 200, 2),
        "revenue_expected_total": round(66 * 25 / 200, 2),
    }


def test_expected_totals_and_gap_equal_the_estimator():
    test, cal = two_arms(10.0, 200, 67, 72)
    out = build_verdict(test, cal)
    totals = [estimate(arm, cal, 60).total for arm in test.arms]
    assert [a["revenue_expected_total"] for a in out["arms"]] == [round(t, 2) for t in totals]
    assert out["expected_gap_per_user"] == round(max(totals) - min(totals), 2)
    assert out["expected_gap_per_user"] >= 0


def test_gap_uses_the_best_other_arm_with_three_arms():
    cal = make_cal({"p": step_curve(15.0)})
    arms = [make_arm("A", 200, 40), make_arm("B", 200, 55), make_arm("C", 200, 66)]
    out = build_verdict(make_test(arms), cal)
    totals = [estimate(arm, cal, 60).total for arm in arms]
    assert out["expected_gap_per_user"] == round(totals[2] - totals[1], 2)


def test_maturity_is_floored_and_the_rule_uses_the_floored_value(monkeypatch):
    test, cal = two_arms(10.0, 200, 67, 72)
    monkeypatch.setattr(verdict_module, "estimate", lambda arm, cal, h: ArmEstimate(0.799996, 0.0, 0.200004))
    out = build_verdict(test, cal)
    assert out["maturity"] == 0.7999
    assert out["reason"] == "pending_revenue"


def test_maturity_floor_tolerates_float_error(monkeypatch):
    test, cal = two_arms(10.0, 200, 67, 72)
    monkeypatch.setattr(verdict_module, "estimate", lambda arm, cal, h: ArmEstimate(0.03, 0.0, 0.27))
    assert build_verdict(test, cal)["maturity"] == 0.1

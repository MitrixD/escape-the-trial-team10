from tests.helpers import make_test
from verdict_agent.calibration import Calibration
from verdict_agent.guardrails import warnings_for
from verdict_agent.model import Arm, Group
from verdict_agent.verdict import build_verdict


def arm(title, users, payers, refunds, trial_cancels=None, events=100):
    groups = [Group("active", "m", 5.0, payers, 10.0), Group("none", "-", 5.0, users - payers, 0.0)]
    return Arm(title, groups, events, 0, payers, refunds, 10.0 * payers, trial_cancels or {})


def refund(w, title):
    return [x for x in w[title] if x["metric"] == "refund_rate_per_payer"]


def test_refunds_per_user_vs_per_payer():
    test = make_test([arm("A", 1000, 109, 12), arm("B", 1000, 218, 29)])
    w = warnings_for(test)
    assert refund(w, "B")[0]["status"] == "ok"
    assert all(x["status"] == "ok" for x in refund(w, "A"))


def test_real_refund_problem_flags_worse():
    test = make_test([arm("A", 1000, 200, 10), arm("B", 1000, 200, 24)])
    w = warnings_for(test)
    b = refund(w, "B")[0]
    assert b["status"] == "worse"
    assert b["value"] == 0.12 and b["vs_other"] == 0.05
    assert refund(w, "A")[0]["status"] == "ok"


def test_ratio_without_significance_is_ok():
    test = make_test([arm("A", 1000, 20, 1), arm("B", 1000, 20, 2)])
    assert refund(warnings_for(test), "B")[0]["status"] == "ok"


def test_no_payers_skips_metric():
    test = make_test([arm("A", 1000, 0, 0), arm("B", 1000, 200, 20)])
    w = warnings_for(test)
    assert refund(w, "A") == []
    assert refund(w, "B") == []


def test_trial_cancel_same_product_only():
    a = arm("A", 1000, 200, 10, {"weekly": (100, 500), "annual": (10, 100)})
    b = arm("B", 1000, 200, 10, {"weekly": (300, 500), "monthly": (50, 100)})
    w = warnings_for(make_test([a, b]))
    weekly = [x for x in w["B"] if x["metric"] == "trial_cancel_rate:weekly"]
    assert weekly[0]["status"] == "worse"
    metrics = {x["metric"] for x in w["A"] + w["B"]}
    assert "trial_cancel_rate:annual" not in metrics and "trial_cancel_rate:monthly" not in metrics


def _verdict(test):
    cal = Calibration({}, {}, {"active": 0.0, "none": 0.0}, "test")
    return build_verdict(test, cal, warnings=warnings_for(test))


def test_real_refund_problem_keeps_verdict():
    test = make_test([arm("A", 1000, 200, 10), arm("B", 1000, 200, 24)])
    cal = Calibration({}, {}, {"active": 0.0, "none": 0.0}, "test")
    base = build_verdict(test, cal)
    out = build_verdict(test, cal, warnings=warnings_for(test))
    for key in ("verdict", "leader", "p2bb_expected", "p2bb_raw", "maturity", "come_back_on", "money_at_stake_usd"):
        assert out[key] == base[key]
    assert out["next_step"]["type"] == base["next_step"]["type"]
    assert out["next_step"]["alternative"] == {"targets": "refund_rate_per_payer"}
    assert out["next_step"]["watch"] == ["refund_rate_per_payer"]
    assert base["next_step"]["alternative"] is None
    assert out["arms"][1]["warnings"][0]["status"] == "worse"


def test_ok_warnings_give_watch_without_alternative():
    out = _verdict(make_test([arm("A", 1000, 109, 12), arm("B", 1000, 218, 29)]))
    assert out["next_step"]["alternative"] is None
    assert out["next_step"]["watch"] == ["refund_rate_per_payer"]

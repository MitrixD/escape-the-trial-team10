import pytest

from verdict_agent.stats import srm_p
from tests.helpers import make_arm, make_cal, make_test, step_curve
from tests.helpers import build_checked_verdict as build_verdict


def weighted(arm, weight=50):
    arm.weight = weight
    return arm


def two(users_a, users_b, days=3, weights=(50, 50)):
    cal = make_cal({"p": step_curve(15.0)})
    a = weighted(make_arm("A", users_a, min(100, users_a)), weights[0])
    b = weighted(make_arm("B", users_b, min(110, users_b)), weights[1])
    return make_test([a, b], days_running=days), cal


def test_srm_p_two_arms_matches_the_chi_square_table():
    assert srm_p([1000, 1000], [50, 50]) == pytest.approx(1.0)
    n = 10000
    x = 3.841459
    a = round(n / 2 + (x * n / 4) ** 0.5)
    assert srm_p([a, n - a], [50, 50]) == pytest.approx(0.05, abs=0.002)


def test_srm_p_three_arms_and_missing_weights():
    assert srm_p([100, 100, 100], [34, 33, 33]) > 0.9
    assert srm_p([100, 100], [50, None]) is None
    assert srm_p([0, 0], [50, 50]) is None


def test_sample_ratio_mismatch():
    out = build_verdict(*two(1400, 1150))
    assert out["health"]["srm"] is True
    assert out["health"]["srm_p"] < 0.001
    assert (out["next_action"], out["next_action_basis"]) == ("fix_test", "health")


def test_balanced_test():
    out = build_verdict(*two(1400, 1400))
    assert out["health"] == {"srm_p": 1.0, "srm": False, "dead_arm": None}
    assert out["next_action_basis"] != "health"


def test_too_few_users_to_call_a_mismatch():
    out = build_verdict(*two(254, 285))
    assert 0.1 < out["health"]["srm_p"] < 0.3
    assert out["health"]["srm"] is False


def test_dead_arm():
    out = build_verdict(*two(0, 300, days=5))
    assert out["health"]["dead_arm"] == "A"
    assert (out["next_action"], out["next_action_basis"]) == ("fix_test", "health")


def test_empty_arm_on_day_one_is_not_dead_yet():
    out = build_verdict(*two(0, 300, days=1))
    assert out["health"]["dead_arm"] is None


def test_missing_weights_give_no_srm():
    test, cal = two(1400, 1150)
    for arm in test.arms:
        arm.weight = None
    out = build_verdict(test, cal)
    assert out["health"]["srm_p"] is None and out["health"]["srm"] is False


UNHEALTHY = {"verdict": "confirmed", "reason": None, "leader": "B", "p2bb_expected": 0.99, "p2bb_raw": 0.98,
             "come_back_on": None, "next_action": "fix_test", "next_action_basis": "health",
             "health": {"srm_p": 7e-07, "srm": True, "dead_arm": None}, "money": None, "arms": []}


def test_card_shows_fix_test_with_srm():
    from verdict_agent.card import render_card
    card = render_card(UNHEALTHY)
    assert card.startswith("FIX TEST · sample ratio mismatch, srm_p 7e-07")


def test_card_shows_dead_arm():
    from verdict_agent.card import render_card
    dead = dict(UNHEALTHY, health={"srm_p": None, "srm": False, "dead_arm": "A"})
    assert render_card(dead).startswith("FIX TEST · dead arm A")


def test_guard_denies_stopping_an_unhealthy_test(monkeypatch):
    from verdict_agent import guard
    monkeypatch.setattr(guard, "safe_verdict", lambda **kw: UNHEALTHY)
    monkeypatch.delenv("VERDICT_GUARD_REPLAY", raising=False)
    decision, reason = guard.decide({"ab_test_id": "t", "app_id": "a", "winner": "x"})
    assert decision == "deny"
    assert "sample ratio mismatch" in reason and "unhealthy" in reason

import pytest

from verdict_agent import verdict as verdict_module
from verdict_agent.model import Arm, Group
from tests.helpers import make_arm, make_cal, make_test, step_curve
from tests.helpers import build_checked_verdict as build_verdict

MONEY_FIELDS = {"traffic_per_day", "after_days", "cost_per_day", "loss_if_ship_leader_now",
                "cost_until_come_back", "chance_leader_is_wrong"}


def certain_arm(title, product, users, value):
    return Arm(title, [Group("active", product, 1.0, users, value)], users, 0, users, users * value)


def certain_test():
    cal = make_cal({"a": [12.0] * 61, "b": [10.0] * 61})
    test = make_test([certain_arm("A", "a", 150, 12.0), certain_arm("B", "b", 150, 10.0)],
                     days_running=3, users_per_day=100.0)
    return test, cal


def test_certain_difference_costs_the_gap_on_the_other_arm_traffic():
    out = build_verdict(*certain_test())
    assert out["leader"] == "A"
    assert set(out["money"]) == MONEY_FIELDS
    assert out["money"]["cost_per_day"] == 100.0
    assert out["money"]["loss_if_ship_leader_now"] == 0.0
    assert out["money"]["traffic_per_day"] == 100.0
    assert out["money"]["after_days"] == 180


def test_after_days_scales_the_loss_of_shipping_now(monkeypatch):
    test, cal = certain_test()
    monkeypatch.setattr(verdict_module, "expected_positive", lambda mu, sd: max(0.0, mu) + 0.01)
    short = verdict_module.build_verdict(test, cal, after_days=30)["money"]["loss_if_ship_leader_now"]
    long = verdict_module.build_verdict(test, cal, after_days=180)["money"]["loss_if_ship_leader_now"]
    assert long == pytest.approx(6 * short)


def test_after_days_below_one_is_rejected():
    test, cal = certain_test()
    with pytest.raises(ValueError, match="after_days must be at least 1"):
        build_verdict_raw(test, cal, after_days=0)


def build_verdict_raw(test, cal, **kw):
    return verdict_module.build_verdict(test, cal, **kw)


def test_no_money_without_data():
    test, cal = certain_test()
    test.arms[0].purchases = 12
    out = build_verdict(test, cal)
    assert out["verdict"] == "not_enough_data"
    assert out["money"] is None
    assert out["next_action"] == "come_back"
    assert out["next_action_basis"] == "verdict"


def test_chance_leader_is_wrong_is_the_complement_of_p2bb():
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 67), make_arm("B", 200, 72)])
    out = build_verdict(test, cal)
    assert out["money"]["chance_leader_is_wrong"] == round(1 - out["p2bb_expected"], 4)


def test_keep_running_prices_the_wait_until_come_back():
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 67), make_arm("B", 200, 72)])
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    days = (verdict_module.date.fromisoformat(out["come_back_on"]) - test.as_of).days
    money = out["money"]
    assert money["cost_until_come_back"] == pytest.approx(money["cost_per_day"] * days, abs=0.005 * days + 0.01)


def test_decided_verdict_has_no_wait_cost():
    out = build_verdict(*certain_test())
    assert out["verdict"] == "confirmed"
    assert out["money"]["cost_until_come_back"] is None


def money_of(loss, wait, p=0.9):
    return {"loss_if_ship_leader_now": loss, "cost_until_come_back": wait, "chance_leader_is_wrong": round(1 - p, 4)}


@pytest.mark.parametrize("verdict,money,p,horizon_reached,action,basis", [
    ("keep_running", money_of(900.0, 4000.0), 0.9, False, "ship_leader", "money"),
    ("keep_running", money_of(2500.0, 300.0), 0.9, False, "come_back", "verdict"),
    ("keep_running", money_of(3273.16, 3282.0), 0.6998, False, "come_back", "verdict"),
    ("keep_running", money_of(10.0, 0.0), 0.70, True, "ship_either", "horizon"),
    ("keep_running", money_of(10.0, 0.0), 0.90, True, "ship_leader", "horizon"),
    ("confirmed", money_of(1.0, None), 0.99, False, "ship_leader", "verdict"),
    ("tie", money_of(1.0, None), 0.6, False, "ship_either", "verdict"),
    ("not_enough_data", None, 0.5, False, "come_back", "verdict"),
])
def test_next_action(verdict, money, p, horizon_reached, action, basis):
    assert verdict_module.next_action(verdict, money, p, horizon_reached) == (action, basis)


def test_unsure_leader_is_not_shipped_on_money():
    cal = make_cal({"p": step_curve(10.0)})
    out = build_verdict(make_test([make_arm("A", 200, 67), make_arm("B", 200, 72)]), cal)
    assert out["verdict"] == "keep_running"
    assert out["p2bb_expected"] < 0.8
    assert out["money"]["cost_until_come_back"] > out["money"]["loss_if_ship_leader_now"]
    assert (out["next_action"], out["next_action_basis"]) == ("come_back", "verdict")


def test_horizon_reached_without_a_winner_ships_either():
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 67), make_arm("B", 200, 72)], days_running=70)
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    assert out["come_back_on"] == test.as_of.isoformat()
    assert (out["next_action"], out["next_action_basis"]) == ("ship_either", "horizon")


def test_horizon_reached_with_a_likely_leader_ships_it(monkeypatch):
    monkeypatch.setattr(verdict_module, "p2bb", lambda xa, xb: 0.9)
    cal = make_cal({"p": step_curve(10.0)})
    test = make_test([make_arm("A", 200, 67), make_arm("B", 200, 72)], days_running=70)
    out = build_verdict(test, cal)
    assert out["verdict"] == "keep_running"
    assert (out["next_action"], out["next_action_basis"]) == ("ship_leader", "horizon")


def test_confirmed_ships_the_leader():
    out = build_verdict(*certain_test())
    assert (out["next_action"], out["next_action_basis"]) == ("ship_leader", "verdict")


def test_synthetic_day14_prices_a_day_and_a_wrong_ship():
    from pathlib import Path
    from verdict_agent import service
    bundle = Path(__file__).parent / "fixtures" / "synthetic" / "day14"
    out = service.verdict("50e46448-6692-54c6-b1e0-1b2e2fa62cdd", replay=str(bundle))
    assert out["leader"] == "weekly_trial"
    assert out["p2bb_raw"] == 0.0
    assert out["money"]["traffic_per_day"] == 200.0
    assert out["money"]["cost_per_day"] == pytest.approx(100 * out["expected_gap_per_user"], rel=0.01)
    assert out["money"]["loss_if_ship_leader_now"] < 100
    assert (out["next_action"], out["next_action_basis"]) == ("ship_leader", "verdict")

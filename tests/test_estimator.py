import pytest

from verdict_agent.estimator import ArmEstimate, estimate, pseudo_values
from verdict_agent.model import Arm, Calibration, Group

STEP = [0.0] * 7 + [10.0] * 60
FLAT = [10.0] * 67
DIP = [10.0] * 30 + [8.0] * 37


def cal(curve=STEP, conv=0.5):
    return Calibration(
        trial_to_paid={"p": conv},
        renewal_value={"p": curve},
        trial_days={"p": 7},
        app_trial_to_paid=None,
        app_renewal_value=None,
        source="test",
    )


def arm(groups):
    return Arm("A", groups, 0, 0, 0, sum(g.n * g.received for g in groups))


def test_pending_trials_raise_expected_above_received():
    a = arm([Group("trial", "p", 3, 10, 0.0), Group("active", "p", 3, 5, 10.0)])
    e = estimate(a, cal(), 60)
    assert e.from_trials == pytest.approx(10 * 0.5 * 10 / 15)
    assert e.total > e.received
    assert e.total == e.received + e.from_trials + e.from_renewals


def test_up_front_only_arm_has_no_positive_renewals():
    a = arm([Group("active", "p", 10, 4, 10.0), Group("ended", "p", 40, 2, 10.0)])
    assert estimate(a, cal(FLAT), 60).from_renewals == pytest.approx(0.0)
    assert estimate(a, cal(DIP), 60).from_renewals <= 0


def test_none_and_ended_add_no_future():
    a = arm([Group("none", "p", 2, 5, 0.0), Group("ended", "p", 20, 5, 4.0)])
    e = estimate(a, cal(), 60)
    assert e.from_trials == 0 and e.from_renewals == 0
    assert e.received == pytest.approx(2.0)


def test_group_mean_equals_per_user_computation():
    c = cal()
    users = (
        [("trial", "p", 2.0, 0.0)] * 7
        + [("trial", "p", 5.0, 0.0)] * 3
        + [("active", "p", 12.0, 10.0)] * 4
        + [("ended", "p", 30.0, 10.0)] * 2
        + [("none", "p", 1.0, 0.0)] * 9
    )
    direct = sum(r + c.expected(s, p, a, 60) for s, p, a, r in users) / len(users)
    groups = [Group(s, p, a, n, r) for (s, p, a, r), n in
              ((k, users.count(k)) for k in dict.fromkeys(users))]
    assert estimate(arm(groups), c, 60).total == pytest.approx(direct, abs=0.01)


def test_zero_users_gives_zeros():
    e = estimate(arm([]), cal(), 60)
    assert e == ArmEstimate(0.0, 0.0, 0.0)
    assert e.total == 0.0
    assert pseudo_values(arm([]), cal(), 60) == []


def test_pseudo_values_mean_equals_total():
    a = arm([Group("trial", "p", 3, 6, 0.0), Group("active", "p", 9, 3, 10.0),
             Group("none", "p", 1, 4, 0.0)])
    vals = pseudo_values(a, cal(), 60)
    assert len(vals) == 13
    assert sum(vals) / len(vals) == pytest.approx(estimate(a, cal(), 60).total)

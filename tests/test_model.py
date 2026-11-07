from datetime import date

from verdict_agent.model import Arm, Calibration, Group, TestData


def cal(**kw):
    base = dict(
        trial_to_paid={}, renewal_value={}, trial_days={},
        app_trial_to_paid=None, app_renewal_value=None, source="none",
    )
    base.update(kw)
    return Calibration(**base)


def test_construct_all():
    g = Group("trial", "p", 2.0, 10, 0.0)
    arm = Arm("A", [g], 1, 10, 0, 0.0)
    t = TestData("id", "t", None, date(2026, 11, 7), date(2026, 11, 8), 5.0, [arm])
    assert t.arms[0].groups[0] is g
    assert cal().source == "none"


def test_arm_users_sums_group_sizes():
    arm = Arm("A", [Group("none", "p", 1, 4, 0), Group("trial", "p", 1, 6, 0)], 0, 6, 0, 0.0)
    assert arm.users == 10
    assert Arm("B", [], 0, 0, 0, 0.0).users == 0


def test_expected_trial_uses_conversion_and_shifted_curve():
    c = cal(trial_to_paid={"p": 0.5}, renewal_value={"p": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]},
            trial_days={"p": 3})
    assert c.expected("trial", "p", 2, 10) == 0.5 * 5


def test_expected_trial_default_length_7():
    c = cal(trial_to_paid={"p": 1.0}, renewal_value={"p": list(range(100))})
    assert c.expected("trial", "p", 1, 20) == 12


def test_expected_active_and_clamp():
    c = cal(trial_to_paid={"p": 1.0}, renewal_value={"p": [0, 1, 2]})
    assert c.expected("active", "p", 5, 10) == 2
    assert c.expected("active", "p", 9, 10) == 1


def test_expected_negative_remaining_is_zero():
    c = cal(trial_to_paid={"p": 1.0}, renewal_value={"p": [0, 1, 2]})
    assert c.expected("active", "p", 10, 10) == 0
    assert c.expected("active", "p", 12, 10) == 0
    assert c.expected("trial", "p", 5, 10) == 0


def test_expected_none_and_ended_zero():
    c = cal(trial_to_paid={"p": 1.0}, renewal_value={"p": [0, 5]})
    assert c.expected("none", "p", 0, 10) == 0
    assert c.expected("ended", "p", 0, 10) == 0


def test_expected_fallback_to_app():
    c = cal(app_trial_to_paid=0.2, app_renewal_value=[0, 10, 20], source="app")
    assert c.expected("trial", "x", 0, 8) == 0.2 * 10
    assert c.expected("active", "x", 0, 8) == 20


def test_expected_empty_product_curve_falls_back():
    c = cal(renewal_value={"p": []}, app_trial_to_paid=0.5, app_renewal_value=[0, 4])
    assert c.expected("active", "p", 0, 5) == 4


def test_expected_no_calibration_is_zero():
    c = cal()
    assert c.expected("trial", "x", 0, 30) == 0
    assert c.expected("active", "x", 0, 30) == 0
    c2 = cal(app_trial_to_paid=0.5)
    assert c2.expected("trial", "x", 0, 30) == 0


def test_source_for():
    c = cal(trial_to_paid={"p": 0.5}, renewal_value={"p": [0, 1]},
            app_trial_to_paid=0.2, app_renewal_value=[0, 1])
    assert c.source_for("p") == "product"
    assert c.source_for("q") == "app"
    assert cal().source_for("q") == "none"

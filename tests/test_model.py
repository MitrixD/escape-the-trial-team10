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


LINEAR = [float(d) for d in range(11)]


def test_expected_trial_is_curve_gain():
    c = cal(trial_to_paid={"p": 0.5}, renewal_value={"p": LINEAR}, trial_days={"p": 3})
    assert c.expected("trial", "p", 2, 10) == 8


def test_expected_trial_never_negative():
    c = cal(trial_to_paid={"p": 0.5}, renewal_value={"p": [5.0, 4.0, 3.0]}, trial_days={"p": 3})
    assert c.expected("trial", "p", 0, 2) == 0


def test_expected_active_with_trial_divides_by_conversion():
    c = cal(trial_to_paid={"p": 0.5}, renewal_value={"p": LINEAR}, trial_days={"p": 3})
    assert c.expected("active", "p", 2, 10) == 16


def test_expected_active_without_trial_is_curve_gain():
    c = cal(renewal_value={"p": LINEAR}, trial_days={"p": 0}, app_trial_to_paid=0.5)
    assert c.expected("active", "p", 2, 10) == 8


def test_expected_active_conversion_falls_back_to_app():
    c = cal(renewal_value={"p": LINEAR}, trial_days={"p": 3}, app_trial_to_paid=0.25)
    assert c.expected("active", "p", 2, 10) == 32


def test_expected_active_with_trial_but_no_conversion_is_curve_gain():
    c = cal(renewal_value={"p": LINEAR}, trial_days={"p": 3})
    assert c.expected("active", "p", 2, 10) == 8


def test_expected_active_may_be_negative_on_falling_curve():
    c = cal(renewal_value={"p": [5.0, 4.0, 3.0]}, trial_days={"p": 0})
    assert c.expected("active", "p", 0, 2) == -2


def test_expected_fractional_age_interpolates():
    c = cal(renewal_value={"p": LINEAR}, trial_days={"p": 0})
    assert c.expected("active", "p", 2.5, 10) == 7.5


def test_expected_horizon_past_curve_is_flat():
    c = cal(renewal_value={"p": [0.0, 1.0, 2.0]}, trial_days={"p": 0})
    assert c.expected("active", "p", 1, 10) == 1


def test_expected_past_horizon_is_zero():
    c = cal(trial_to_paid={"p": 1.0}, renewal_value={"p": LINEAR}, trial_days={"p": 3})
    assert c.expected("active", "p", 10, 10) == 0
    assert c.expected("active", "p", 12, 10) == 0
    assert c.expected("trial", "p", 12, 10) == 0


def test_expected_none_and_ended_zero():
    c = cal(trial_to_paid={"p": 1.0}, renewal_value={"p": [0, 5]})
    assert c.expected("none", "p", 0, 10) == 0
    assert c.expected("ended", "p", 0, 10) == 0


def test_expected_fallback_to_app():
    c = cal(app_trial_to_paid=0.2, app_renewal_value=[0, 10, 20], source="app")
    assert c.expected("trial", "x", 0, 2) == 20
    assert c.expected("active", "x", 0, 2) == 100


def test_expected_empty_product_curve_falls_back():
    c = cal(renewal_value={"p": []}, trial_days={"p": 0}, app_renewal_value=[0, 4])
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
    assert cal(trial_to_paid={"p": 0.5}, app_trial_to_paid=0.5).source_for("p") == "none"

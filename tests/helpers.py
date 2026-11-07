from datetime import date, timedelta

from verdict_agent.model import Arm, Calibration, Group, TestData

START = date(2026, 11, 7)


def step_curve(gain, base=10.0, horizon=60):
    return [base] * 31 + [base + gain] * (horizon - 30)


def make_cal(curves, conv=0.5, trial_days=None, source="product"):
    return Calibration(
        trial_to_paid={p: conv for p in curves},
        renewal_value=dict(curves),
        trial_days=dict(trial_days) if trial_days is not None else {p: 7 for p in curves},
        app_trial_to_paid=None,
        app_renewal_value=None,
        source=source,
    )


def make_arm(title, users, payers, received=10.0, status="active", product="p", age=3, purchases=40, trials=0):
    groups = [Group("none", product, age, users - payers, 0.0), Group(status, product, age, payers, received)]
    return Arm(title, groups, purchases, trials, payers if status == "active" else 0, payers * received)


def make_test(arms, days_running=3, users_per_day=100.0, started_on=START, title="Paywall test"):
    return TestData(
        ab_test_id="test-1",
        title=title,
        placement_id=None,
        started_on=started_on,
        as_of=started_on + timedelta(days=days_running),
        users_per_day=users_per_day,
        arms=arms,
    )


def build_checked_verdict(test, cal, horizon=None):
    from tests.schema_check import assert_valid
    from verdict_agent.verdict import build_verdict

    out = build_verdict(test, cal, horizon)
    assert_valid(out)
    return out

import math
from datetime import date, timedelta

from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.model import DEFAULT_TRIAL_DAYS, Arm, Calibration, TestData, VerdictError
from verdict_agent.stats import diff_ci, diff_mean_se, expected_positive, p2bb, users_needed

MIN_EVENTS = 30
P_CONFIRM = 0.95
P_MONEY_MIN = 0.80
MATURITY_MIN = 0.80
MDE_SHARE = 0.05
DEFAULT_HORIZON = 60
DEFAULT_AFTER_DAYS = 180
RENEWAL_DAYS = 30
FLOOR_EPS = 1e-9


def _floor4(p: float) -> float:
    return math.floor(p * 1e4 + FLOOR_EPS) / 1e4


def _events(arm: Arm) -> int:
    return arm.purchases + arm.trials if arm.users > 0 else 0


def _received_values(arm: Arm) -> list[float]:
    values: list[float] = []
    for g in arm.groups:
        values.extend([g.received] * g.n)
    return values


def _per_user(x: float) -> float:
    return round(x, 2) + 0.0


def check_horizon(horizon: int | None) -> int:
    if horizon is None:
        return DEFAULT_HORIZON
    if horizon < 1:
        raise VerdictError("horizon must be at least 1 day")
    return horizon


def check_after_days(after_days: int | None) -> int:
    if after_days is None:
        return DEFAULT_AFTER_DAYS
    if after_days < 1:
        raise VerdictError("after_days must be at least 1")
    return after_days


def build_verdict(test: TestData, cal: Calibration, horizon: int | None = None,
                  after_days: int | None = None) -> dict:
    horizon = check_horizon(horizon)
    after_days = check_after_days(after_days)
    if len(test.arms) < 2:
        raise VerdictError("an A/B test needs at least two arms")
    estimates = [estimate(arm, cal, horizon) for arm in test.arms]
    totals = [e.total for e in estimates]
    leader_i = max(range(len(test.arms)), key=lambda i: (totals[i], -i))
    other_i = max((i for i in range(len(test.arms)) if i != leader_i), key=lambda i: (totals[i], -i))
    leader, other = test.arms[leader_i], test.arms[other_i]

    leader_values, other_values = pseudo_values(leader, cal, horizon), pseudo_values(other, cal, horizon)
    p_expected = _floor4(p2bb(other_values, leader_values))
    p_raw = _floor4(p2bb(_received_values(other), _received_values(leader)))

    received_sum = sum(arm.users * e.received for arm, e in zip(test.arms, estimates))
    total_sum = sum(arm.users * e.total for arm, e in zip(test.arms, estimates))
    maturity = _floor4(received_sum / total_sum) if total_sum else 1.0

    min_events = min(_events(arm) for arm in test.arms)
    if min_events < MIN_EVENTS:
        verdict, reason = "not_enough_data", "min_events"
    elif cal.source == "none":
        verdict, reason = "not_enough_data", "no_calibration"
    elif p_expected >= P_CONFIRM:
        verdict, reason = "confirmed", None
    elif maturity >= MATURITY_MIN and _diff_bound(other_values, leader_values) < MDE_SHARE * totals[leader_i]:
        verdict, reason = "tie", None
    else:
        verdict, reason = "keep_running", "pending_revenue" if maturity < MATURITY_MIN else "underpowered"

    come_back_on = None
    if reason == "min_events":
        come_back_on = _min_events_date(test, min_events)
    elif verdict == "keep_running":
        come_back_on = _keep_running_date(test, cal, horizon, other_values, leader_values)

    money = None
    if verdict != "not_enough_data":
        money = money_at_stake(test, leader, other, leader_values, other_values, p_expected, after_days,
                               come_back_on if verdict == "keep_running" else None)
    action, basis = next_action(verdict, money, p_expected, come_back_on == test.as_of)

    return {
        "ab_test_id": test.ab_test_id,
        "verdict": verdict,
        "reason": reason,
        "leader": leader.title,
        "p2bb_expected": p_expected,
        "p2bb_raw": p_raw,
        "maturity": maturity,
        "horizon_days": horizon,
        "come_back_on": come_back_on.isoformat() if come_back_on else None,
        "arms": [
            {
                "title": arm.title,
                "users": arm.users,
                "revenue_received": _per_user(e.received),
                "revenue_expected_trials": _per_user(e.from_trials),
                "revenue_expected_renewals": _per_user(e.from_renewals),
                "revenue_expected_total": _per_user(e.total),
            }
            for arm, e in zip(test.arms, estimates)
        ],
        "calibration_source": cal.source,
        "expected_gap_per_user": _per_user(max(0.0, totals[leader_i] - totals[other_i])),
        "money": money,
        "next_action": action,
        "next_action_basis": basis,
    }


def _days_running(test: TestData) -> int:
    return max(1, (test.as_of - test.started_on).days)


def money_at_stake(test, leader, other, leader_values, other_values, p_expected, after_days, come_back_on):
    delta, se = diff_mean_se(leader_values, other_values)
    days = _days_running(test)
    cost_per_day = (other.users * expected_positive(-delta, se) + leader.users * expected_positive(delta, se)) / days
    loss_now = after_days * test.users_per_day * expected_positive(delta, se)
    wait = cost_per_day * (come_back_on - test.as_of).days if come_back_on else None
    return {
        "traffic_per_day": round(test.users_per_day, 1),
        "after_days": after_days,
        "cost_per_day": round(cost_per_day, 2) + 0.0,
        "loss_if_ship_leader_now": round(loss_now, 2) + 0.0,
        "cost_until_come_back": round(wait, 2) + 0.0 if wait is not None else None,
        "chance_leader_is_wrong": round(1 - p_expected, 4),
    }


def next_action(verdict: str, money: dict | None, p_expected: float, horizon_reached: bool) -> tuple[str, str]:
    if verdict == "confirmed":
        return "ship_leader", "verdict"
    if verdict == "tie":
        return "ship_either", "verdict"
    if verdict != "keep_running" or money is None:
        return "come_back", "verdict"
    likely = p_expected >= P_MONEY_MIN
    if horizon_reached:
        return ("ship_leader" if likely else "ship_either"), "horizon"
    if likely and money["loss_if_ship_leader_now"] < money["cost_until_come_back"]:
        return "ship_leader", "money"
    return "come_back", "verdict"


def _diff_bound(other_values: list[float], leader_values: list[float]) -> float:
    lo, hi = diff_ci(other_values, leader_values)
    return max(abs(lo), abs(hi))


def _min_events_date(test: TestData, min_events: int) -> date | None:
    if min_events == 0:
        return None
    days_since_start = max(1, (test.as_of - test.started_on).days)
    days_needed = -(-(MIN_EVENTS - min_events) * days_since_start // min_events)
    return test.as_of + timedelta(days=days_needed)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pooled_sd(xa: list[float], xb: list[float]) -> float:
    dof = len(xa) + len(xb) - 2
    if dof < 1:
        return 0.0
    ma, mb = _mean(xa), _mean(xb)
    ss = sum((x - ma) ** 2 for x in xa) + sum((x - mb) ** 2 for x in xb)
    return math.sqrt(ss / dof)


def _keep_running_date(test, cal, horizon, other_values, leader_values) -> date:
    cap = test.started_on + timedelta(days=horizon)
    products = {g.product for arm in test.arms for g in arm.groups if g.status == "trial"}
    longest_trial = max((cal.trial_days.get(p, DEFAULT_TRIAL_DAYS) for p in products), default=0)
    target = test.started_on + timedelta(days=longest_trial + RENEWAL_DAYS)
    delta = abs(_mean(leader_values) - _mean(other_values))
    if delta > 0:
        missing = users_needed(delta, _pooled_sd(other_values, leader_values)) - min(len(other_values), len(leader_values))
        per_day = test.users_per_day / len(test.arms)
        if missing > 0:
            days = math.ceil(missing / per_day) if per_day > 0 else math.inf
            target = max(target, test.as_of + timedelta(days=min(days, max((cap - test.as_of).days, 0))))
    return max(min(target, cap), test.as_of)

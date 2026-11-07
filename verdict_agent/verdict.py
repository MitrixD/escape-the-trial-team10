import math

from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.model import Arm, Calibration, TestData
from verdict_agent.stats import diff_ci, p2bb

MIN_EVENTS = 30
P_CONFIRM = 0.95
MATURITY_MIN = 0.80
MDE_SHARE = 0.05
DEFAULT_HORIZON = 60


def _floor4(p: float) -> float:
    return math.floor(p * 1e4) / 1e4


def _events(arm: Arm) -> int:
    return arm.purchases + arm.trials if arm.users > 0 else 0


def _received_values(arm: Arm) -> list[float]:
    values: list[float] = []
    for g in arm.groups:
        values.extend([g.received] * g.n)
    return values


def _per_user(x: float) -> float:
    return round(x, 2) + 0.0


def build_verdict(test: TestData, cal: Calibration, horizon: int | None = None) -> dict:
    horizon = DEFAULT_HORIZON if horizon is None else horizon
    if len(test.arms) < 2:
        raise ValueError("an A/B test needs at least two arms")
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
    maturity = received_sum / total_sum if total_sum else 1.0

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

    return {
        "ab_test_id": test.ab_test_id,
        "verdict": verdict,
        "reason": reason,
        "leader": leader.title,
        "p2bb_expected": p_expected,
        "p2bb_raw": p_raw,
        "maturity": round(maturity, 4),
        "horizon_days": horizon,
        "come_back_on": None,
        "arms": [
            {
                "title": arm.title,
                "users": arm.users,
                "revenue_received": _per_user(e.received),
                "revenue_expected_trials": _per_user(e.from_trials),
                "revenue_expected_renewals": _per_user(e.from_renewals),
            }
            for arm, e in zip(test.arms, estimates)
        ],
        "calibration_source": cal.source,
    }


def _diff_bound(other_values: list[float], leader_values: list[float]) -> float:
    lo, hi = diff_ci(other_values, leader_values)
    return max(abs(lo), abs(hi))

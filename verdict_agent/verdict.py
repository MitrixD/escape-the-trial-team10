import re
from datetime import timedelta

from verdict_agent.calibration import Calibration
from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.model import Arm, TestData
from verdict_agent.stats import p2bb

MIN_EVENTS = 30
P_CONFIRM = 0.95
MATURITY_MIN = 0.80
DECISION_LIFETIME_DAYS = 180
DEFAULT_HORIZON = 60
RENEWAL_DAYS = 30
DEFAULT_TRIAL_DAYS = 7

NEXT_STEP = {
    "not_enough_data": ("extend", "Keep the test running until every arm has 30 purchases and trials."),
    "early": ("extend", "Keep the test running until pending trials and first renewals have matured."),
    "confirmed": ("stop_with_winner", "Stop the test and roll out the leader."),
    "tie": ("change_lever", "Do not repeat the same test: change the lever or make the variant bolder."),
}


def horizon_from_goal(goal: str) -> int:
    match = re.search(r"(\d+)[- ]day", goal or "")
    return int(match.group(1)) if match else DEFAULT_HORIZON


def _events(arm: Arm) -> int:
    return arm.purchases + arm.trials if arm.users > 0 else 0


def _received_values(arm: Arm) -> list[float]:
    values: list[float] = []
    for g in arm.groups:
        values.extend([g.received] * g.n)
    return values


def _come_back_on(verdict, test, horizon, min_events, trial_days):
    if verdict == "not_enough_data":
        if min_events == 0:
            return None
        days_since_start = max(1, (test.as_of - test.started_on).days)
        days_needed = -(-(MIN_EVENTS - min_events) * days_since_start // min_events)
        return test.as_of + timedelta(days=days_needed)
    if verdict == "early":
        trial_days = trial_days or {}
        products = {g.product for arm in test.arms for g in arm.groups if g.status == "trial"}
        slowest = max((trial_days.get(p, DEFAULT_TRIAL_DAYS) for p in products), default=0)
        return max(test.as_of, test.started_on + timedelta(days=min(slowest + RENEWAL_DAYS, horizon)))
    return None


def build_verdict(
    test: TestData,
    cal: Calibration,
    warnings: dict[str, list[dict]] | None = None,
    segments: tuple[int, list[dict]] | None = None,
    trial_days: dict[str, int] | None = None,
) -> dict:
    horizon = horizon_from_goal(test.goal)
    estimates = [estimate(arm, cal) for arm in test.arms]
    totals = [e.total for e in estimates]
    leader_i = max(range(len(test.arms)), key=lambda i: (totals[i], -i))
    other_i = max((i for i in range(len(test.arms)) if i != leader_i), key=lambda i: (totals[i], -i))
    leader, other = test.arms[leader_i], test.arms[other_i]

    p_expected = p2bb(pseudo_values(other, cal), pseudo_values(leader, cal))
    p_raw = p2bb(_received_values(other), _received_values(leader))

    received_sum = sum(arm.users * e.received for arm, e in zip(test.arms, estimates))
    total_sum = sum(arm.users * e.total for arm, e in zip(test.arms, estimates))
    maturity = received_sum / total_sum if total_sum else 1.0

    min_events = min(_events(arm) for arm in test.arms)
    if min_events < MIN_EVENTS:
        verdict = "not_enough_data"
    elif p_expected >= P_CONFIRM:
        verdict = "confirmed"
    elif maturity < MATURITY_MIN:
        verdict = "early"
    else:
        verdict = "tie"

    come_back_on = _come_back_on(verdict, test, horizon, min_events, trial_days)
    money = abs(totals[leader_i] - totals[other_i]) * test.users_per_day * DECISION_LIFETIME_DAYS * (1 - p_expected)
    warnings = warnings or {}
    checked, found = segments or (0, [])
    step_type, reason = NEXT_STEP[verdict]
    all_warnings = [w for arm in test.arms for w in warnings.get(arm.title, [])]
    watch = sorted({w["metric"] for w in all_warnings})
    worse = next((w for w in all_warnings if w["status"] == "worse"), None)

    return {
        "ab_test_id": test.ab_test_id,
        "verdict": verdict,
        "leader": leader.title,
        "p2bb_expected": round(p_expected, 4),
        "p2bb_raw": round(p_raw, 4),
        "horizon_days": horizon,
        "maturity": round(maturity, 4),
        "come_back_on": come_back_on.isoformat() if come_back_on else None,
        "money_at_stake_usd": round(money, 2),
        "arms": [
            {
                "title": arm.title,
                "users": arm.users,
                "revenue_received": round(e.received, 2),
                "revenue_expected_trials": round(e.from_trials, 2),
                "revenue_expected_renewals": round(e.from_renewals, 2),
                "warnings": list(warnings.get(arm.title, [])),
            }
            for arm, e in zip(test.arms, estimates)
        ],
        "segments_checked": checked,
        "segments_found": list(found),
        "next_step": {
            "type": step_type,
            "reason": reason,
            "placement_id": test.placement_id,
            "primary_metric": f"net revenue per user, {horizon} days",
            "watch": watch,
            "alternative": {"targets": worse["metric"]} if worse else None,
        },
        "source": test.source,
        "calibration_source": cal.source,
    }

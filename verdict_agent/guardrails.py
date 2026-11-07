from verdict_agent.model import TestData
from verdict_agent.stats import two_prop_p

GUARD_RATIO = 1.5
ALPHA = 0.05


def _rate(k: int, n: int) -> float:
    return k / n


def _compare(metric: str, counts: dict[str, tuple[int, int]]) -> dict[str, dict]:
    out = {}
    for title, (k, n) in counts.items():
        if n == 0:
            continue
        others = {t: c for t, c in counts.items() if t != title and c[1] > 0}
        if not others:
            continue
        value = _rate(k, n)
        best = min(others, key=lambda t: _rate(*others[t]))
        ok, on = others[best]
        vs_other = _rate(ok, on)
        worse = vs_other > 0 and value >= GUARD_RATIO * vs_other and two_prop_p(ok, on, k, n) < ALPHA
        if not worse and vs_other == 0 and value > 0:
            worse = two_prop_p(ok, on, k, n) < ALPHA
        out[title] = {
            "metric": metric,
            "value": round(value, 4),
            "vs_other": round(vs_other, 4),
            "status": "worse" if worse else "ok",
        }
    return out


def warnings_for(test: TestData) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {arm.title: [] for arm in test.arms}
    refunds = {arm.title: (arm.refunds, arm.paid_users) for arm in test.arms}
    for title, w in _compare("refund_rate_per_payer", refunds).items():
        result[title].append(w)
    products = sorted({p for arm in test.arms for p in arm.trial_cancels})
    for product in products:
        counts = {
            arm.title: arm.trial_cancels[product]
            for arm in test.arms
            if product in arm.trial_cancels
        }
        if len(counts) < 2:
            continue
        for title, w in _compare(f"trial_cancel_rate:{product}", counts).items():
            result[title].append(w)
    return result

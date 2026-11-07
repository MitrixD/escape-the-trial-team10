from verdict_agent.stats import bonferroni, diff_in_diff_p

SEGMENT_MIN_USERS = 100
ALPHA = 0.05
DIMENSIONS = ["platform", "acquisition_channel", "onboarding_goal", "push_opt_in"]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def check_segments(
    rows: dict[str, list[tuple[dict, float]]], dimensions: list[str] | None = None
) -> tuple[int, list[dict]]:
    arms = list(rows)[:2]
    if len(arms) < 2:
        return 0, []
    a, b = arms
    tested: list[tuple[str, str, float, float]] = []
    for dim in dimensions or DIMENSIONS:
        values = sorted({str(attrs.get(dim)) for arm in arms for attrs, _ in rows[arm] if attrs.get(dim) is not None})
        for value in values:
            split = {}
            for arm in arms:
                inside = [v for attrs, v in rows[arm] if str(attrs.get(dim)) == value]
                outside = [v for attrs, v in rows[arm] if attrs.get(dim) is not None and str(attrs.get(dim)) != value]
                split[arm] = (inside, outside)
            if any(len(part) < SEGMENT_MIN_USERS for pair in split.values() for part in pair):
                continue
            p = diff_in_diff_p(split[a][0], split[b][0], split[a][1], split[b][1])
            lift = _mean(split[b][0]) - _mean(split[a][0])
            tested.append((dim, value, lift, p))
    adjusted = bonferroni([t[3] for t in tested])
    found = [
        {"dimension": dim, "value": value, "lift": round(lift, 4), "p_adjusted": round(p_adj, 4)}
        for (dim, value, lift, _), p_adj in zip(tested, adjusted)
        if p_adj < ALPHA
    ]
    return len(tested), found

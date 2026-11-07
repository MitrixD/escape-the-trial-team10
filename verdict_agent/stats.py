import math


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _mean_var(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    return m, sum((x - m) ** 2 for x in xs) / (n - 1)


def p2bb(xa: list[float], xb: list[float]) -> float:
    na, nb = len(xa), len(xb)
    if na < 2 or nb < 2:
        return 0.5
    ma, va = _mean_var(xa)
    mb, vb = _mean_var(xb)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 0.5 if ma == mb else (1.0 if mb > ma else 0.0)
    return _phi((mb - ma) / se)


def two_prop_p(k1: int, n1: int, k2: int, n2: int) -> float:
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    var = pooled * (1 - pooled) * (1 / n1 + 1 / n2)
    if p1 == p2 or var == 0:
        return 1.0
    z = (p2 - p1) / math.sqrt(var)
    return 2 * (1 - _phi(abs(z)))


def welch_p(xa: list[float], xb: list[float]) -> float:
    if len(xa) < 2 or len(xb) < 2:
        return 1.0
    ma, va = _mean_var(xa)
    mb, vb = _mean_var(xb)
    se = math.sqrt(va / len(xa) + vb / len(xb))
    if se == 0:
        return 1.0 if ma == mb else 0.0
    return 2 * (1 - _phi(abs(mb - ma) / se))


def diff_in_diff_p(
    seg_a: list[float], seg_b: list[float], rest_a: list[float], rest_b: list[float]
) -> float:
    if min(len(seg_a), len(seg_b), len(rest_a), len(rest_b)) < 2:
        return 1.0
    stats = [_mean_var(g) for g in (seg_a, seg_b, rest_a, rest_b)]
    lens = [len(g) for g in (seg_a, seg_b, rest_a, rest_b)]
    diff = (stats[1][0] - stats[0][0]) - (stats[3][0] - stats[2][0])
    se = math.sqrt(sum(v / n for (_, v), n in zip(stats, lens)))
    if se == 0:
        return 1.0 if diff == 0 else 0.0
    return 2 * (1 - _phi(abs(diff) / se))


def bonferroni(ps: list[float]) -> list[float]:
    m = len(ps)
    return [min(1.0, p * m) for p in ps]

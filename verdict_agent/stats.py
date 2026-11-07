import math
from statistics import NormalDist


def _mean_var(xs):
    n = len(xs)
    m = sum(xs) / n
    return m, sum((x - m) ** 2 for x in xs) / (n - 1)


def p2bb(xa, xb):
    na, nb = len(xa), len(xb)
    if na < 2 or nb < 2:
        return 0.5
    ma, va = _mean_var(xa)
    mb, vb = _mean_var(xb)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 0.5 if ma == mb else (1.0 if mb > ma else 0.0)
    return 0.5 * (1 + math.erf((mb - ma) / se / math.sqrt(2)))


def diff_ci(xa, xb, level=0.95):
    na, nb = len(xa), len(xb)
    if na < 2 or nb < 2:
        return (-math.inf, math.inf)
    ma, va = _mean_var(xa)
    mb, vb = _mean_var(xb)
    half = NormalDist().inv_cdf((1 + level) / 2) * math.sqrt(va / na + vb / nb)
    return (mb - ma - half, mb - ma + half)


def users_needed(delta, sd, level=0.95, power=0.8):
    if delta <= 0 or sd < 0:
        raise ValueError("delta must be positive and sd non-negative")
    if sd == 0:
        return 1
    nd = NormalDist()
    z = nd.inv_cdf(1 - (1 - level) / 2) + nd.inv_cdf(power)
    return math.ceil(2 * (z * sd / delta) ** 2)


def diff_mean_se(xa, xb):
    na, nb = len(xa), len(xb)
    if na < 2 or nb < 2:
        return (sum(xb) / nb if nb else 0.0) - (sum(xa) / na if na else 0.0), math.inf
    ma, va = _mean_var(xa)
    mb, vb = _mean_var(xb)
    return mb - ma, math.sqrt(va / na + vb / nb)


def expected_positive(mu, sd):
    if sd == 0:
        return max(0.0, mu)
    if math.isinf(sd):
        return math.inf
    nd = NormalDist()
    z = mu / sd
    return mu * nd.cdf(z) + sd * nd.pdf(z)

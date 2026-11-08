import math
import random
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


def srm_p(users, weights):
    if any(w is None or w <= 0 for w in weights) or sum(users) == 0 or len(users) not in (2, 3):
        return None
    total, wsum = sum(users), sum(weights)
    x = sum((u - total * w / wsum) ** 2 / (total * w / wsum) for u, w in zip(users, weights))
    return math.erfc(math.sqrt(x / 2)) if len(users) == 2 else math.exp(-x / 2)


def p_best(arms_values, leader, draws=20000, seed=0):
    """Chance that arm `leader` has the highest mean, drawing each mean from its normal approximation."""
    params = []
    for values in arms_values:
        n = len(values)
        if n < 2:
            return 0.5
        m, v = _mean_var(values)
        params.append((m, math.sqrt(v / n)))
    rng = random.Random(seed)
    wins = 0
    for _ in range(draws):
        draws_i = [rng.gauss(m, s) if s > 0 else m for m, s in params]
        if max(range(len(draws_i)), key=lambda i: (draws_i[i], i == leader)) == leader:
            wins += 1
    return wins / draws


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

"""Spike eval for the A/B co-pilot idea (K1, K2). Throwaway: validates the idea before any product code.

Simulates running each historical A/B test from the offline Lumen dataset at a fixed daily traffic,
and checks, per decision day, how often each rule calls the wrong winner versus the truth
(net revenue per user at HORIZON days after install, full population).

Rules:
  naive  - P2BB on revenue observed so far (what the dashboard/CLI shows); declare at >= 95%.
  guard  - P2BB on expected HORIZON-day revenue per user: observed + mean future revenue of users
           in the same state (none / trial / active sub / ended) and age, learned from users NOT in the test.
"""
import csv
import gzip
import math
import random
import sys
from collections import defaultdict
from datetime import datetime

DATA = sys.argv[1] if len(sys.argv) > 1 else "adapty-seed-data-hack/data/offline"
HORIZON = int(sys.argv[2]) if len(sys.argv) > 2 else 60
DATA_END = datetime.fromisoformat("2026-11-03T00:00:00+00:00")
DAYS = [1, 3, 7, 14, 21, 28]
TRAFFIC = [30, 100]
REPS = 150
THRESH = 0.95
random.seed(7)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load():
    users = {u["user_id"]: u for u in csv.DictReader(gzip.open(f"{DATA}/users.csv.gz", "rt"))}
    tx = defaultdict(list)
    for t in csv.DictReader(gzip.open(f"{DATA}/transactions.csv.gz", "rt")):
        tx[t["user_id"]].append(t)
    out = {}
    for uid, u in users.items():
        inst = ts(u["install_at"])
        if (DATA_END - inst).days < HORIZON:
            continue
        ev, subs = [], []
        for t in tx[uid]:
            a = (ts(t["purchased_at"]) - inst).total_seconds() / 86400
            p = float(t["price_usd"] or 0)
            ev.append((a, p))
            if t["refunded_at"]:
                ev.append(((ts(t["refunded_at"]) - inst).total_seconds() / 86400, -p))
            exp = (ts(t["expires_at"]) - inst).total_seconds() / 86400 if t["expires_at"] else 1e9
            subs.append((a, exp, t["product"], t["offer"] == "free_trial"))
        out[uid] = {"test": u["ab_test"], "arm": u["flow"], "ev": ev, "subs": sorted(subs)}
    return out


def rev(u, age):
    return sum(p for a, p in u["ev"] if a <= age)


def state(u, age):
    cur = [s for s in u["subs"] if s[0] <= age]
    if not cur:
        return ("none", "-")
    start, exp, prod, trial = cur[-1]
    if exp > age:
        return ("trial" if trial else "active", prod)
    return ("ended", prod)


def calibrate(history):
    acc = defaultdict(lambda: [0.0, 0])
    for u in history:
        r_h = rev(u, HORIZON)
        for age in range(HORIZON + 1):
            k = (state(u, age), age)
            acc[k][0] += r_h - rev(u, age)
            acc[k][1] += 1
    table = {k: s / n for k, (s, n) in acc.items()}
    by_state = defaultdict(lambda: [0.0, 0])
    for (st, age), (s, n) in acc.items():
        by_state[st][0] += s
        by_state[st][1] += n
    fallback = {st: s / n for st, (s, n) in by_state.items()}
    return table, fallback


def predict(u, age, table, fallback):
    st = state(u, age)
    a = min(HORIZON, int(age))
    return rev(u, age) + table.get((st, a), fallback.get(st, 0.0))


def p2bb(xa, xb):
    """P(mean B > mean A), normal approximation of the posterior of the mean."""
    na, nb = len(xa), len(xb)
    if na < 2 or nb < 2:
        return 0.5
    ma, mb = sum(xa) / na, sum(xb) / nb
    va = sum((x - ma) ** 2 for x in xa) / (na - 1)
    vb = sum((x - mb) ** 2 for x in xb) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 0.5 if ma == mb else (1.0 if mb > ma else 0.0)
    return 0.5 * (1 + math.erf((mb - ma) / se / math.sqrt(2)))


def run():
    users = load()
    tests = sorted({u["test"] for u in users.values() if u["test"]})
    print(f"horizon={HORIZON}d users_with_history={len(users)} reps={REPS} declare_at={THRESH:.0%}")
    for test in tests:
        pop = defaultdict(list)
        for u in users.values():
            if u["test"] == test:
                pop[u["arm"]].append(u)
        history = [u for u in users.values() if u["test"] != test]
        table, fallback = calibrate(history)
        arms = sorted(pop)
        a_name, b_name = arms
        truth = {k: sum(rev(u, HORIZON) for u in v) / len(v) for k, v in pop.items()}
        tp = p2bb([rev(u, HORIZON) for u in pop[a_name]], [rev(u, HORIZON) for u in pop[b_name]])
        winner = b_name if truth[b_name] > truth[a_name] else a_name
        print(f"\n=== {test}")
        print("  truth ARPU@%dd: " % HORIZON + ", ".join(f"{k}=${v:.2f} (n={len(pop[k])})" for k, v in truth.items())
              + f"  winner={winner}  P2BB(full data)={max(tp, 1 - tp):.2f}")
        for traffic in TRAFFIC:
            print(f"  traffic {traffic}/day/arm")
            print("   day | naive: wrong-lead declared-wrong declared-right | guard: wrong-lead declared-wrong declared-right")
            for day in DAYS:
                stats = {"naive": [0, 0, 0], "guard": [0, 0, 0]}
                for _ in range(REPS):
                    obs = {}
                    for arm in arms:
                        n = traffic * day
                        sample = [random.choice(pop[arm]) for _ in range(n)]
                        ages = [day - (i // traffic) - random.random() for i in range(n)]
                        obs[arm] = (sample, ages)
                    for rule in ("naive", "guard"):
                        vals = {}
                        for arm, (sample, ages) in obs.items():
                            if rule == "naive":
                                vals[arm] = [rev(u, a) for u, a in zip(sample, ages)]
                            else:
                                vals[arm] = [predict(u, a, table, fallback) for u, a in zip(sample, ages)]
                        pb = p2bb(vals[a_name], vals[b_name])
                        lead = b_name if pb > 0.5 else a_name
                        s = stats[rule]
                        s[0] += lead != winner
                        if max(pb, 1 - pb) >= THRESH:
                            s[1] += lead != winner
                            s[2] += lead == winner
                f = lambda s: "  ".join(f"{x / REPS:6.0%}" for x in s)
                print(f"   {day:>3} | {f(stats['naive'])}       | {f(stats['guard'])}")


if __name__ == "__main__":
    run()

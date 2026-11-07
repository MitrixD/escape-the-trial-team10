"""Spike: expected money lost per A/B test by decision rule, versus an oracle that always ships the true winner.

Daily peeking, as people do in the dashboard. Loss has two parts:
  during the test  - half of the placement traffic sees the losing arm: 0.5 * traffic * gap per day;
  after the stop   - if the wrong arm ships, all placement traffic sees it for AFTER days: traffic * gap per day.
gap = difference in net revenue per user at HORIZON days (the truth from the full population).

Rules:
  naive  - stop on the first day raw P2BB >= 95%; at MAX_DAYS ship the current leader.
  wait14 - Adapty's proxy (ARPU after 14 days): ship the raw-P2BB leader on day 14.
  guard  - stop on the first day P2BB on expected HORIZON-day revenue >= 95%; at MAX_DAYS ship its leader.
"""
import importlib.util
import random
import sys
from collections import defaultdict
from pathlib import Path

spec = importlib.util.spec_from_file_location("ev", Path(__file__).with_name("ab_verdict_eval.py"))
ev = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]] + sys.argv[1:]
spec.loader.exec_module(ev)

MAX_DAYS = 28
AFTER = 180
REPS = 120
LUMEN_INSTALLS = 420
PLACEMENT_SHARE = {"Main: 3 plans vs lifetime anchor (NA)": 0.266,
                   "Onboarding: annual trial vs weekly first": 0.551,
                   "Settings: upgrade vs lifetime anchor": 0.070}
SCALES = [1, 10]
random.seed(11)


def curves(u, table, fallback):
    top = MAX_DAYS + 1
    raw = [ev.rev(u, a + 0.5) for a in range(top)]
    pred = [ev.predict(u, a + 0.5, table, fallback) for a in range(top)]
    return raw, pred


def run():
    users = ev.load()
    print(f"horizon={ev.HORIZON}d  after-stop={AFTER}d  max test={MAX_DAYS}d  reps={REPS}  Lumen installs/day={LUMEN_INSTALLS}")
    for test, share in PLACEMENT_SHARE.items():
        pop = defaultdict(list)
        for u in users.values():
            if u["test"] == test:
                pop[u["arm"]].append(u)
        table, fallback = ev.calibrate([u for u in users.values() if u["test"] != test])
        a_name, b_name = sorted(pop)
        truth = {k: sum(ev.rev(u, ev.HORIZON) for u in v) / len(v) for k, v in pop.items()}
        winner = max(truth, key=truth.get)
        gap = abs(truth[a_name] - truth[b_name])
        cache = {id(u): curves(u, table, fallback) for v in pop.values() for u in v}
        print(f"\n=== {test}\n  gap ${gap:.2f}/user at {ev.HORIZON}d, winner {winner}")
        for scale in SCALES:
            traffic = LUMEN_INSTALLS * share * scale
            per_arm = max(1, round(traffic / 2))
            res = {r: [0.0, 0, 0.0] for r in ("naive", "wait14", "guard")}
            for _ in range(REPS):
                sample = {arm: [cache[id(random.choice(pop[arm]))] for _ in range(per_arm * MAX_DAYS)] for arm in pop}
                stop = {}
                for day in range(1, MAX_DAYS + 1):
                    n = per_arm * day
                    vals = {}
                    for kind, idx in (("raw", 0), ("pred", 1)):
                        vals[kind] = {arm: [s[idx][day - 1 - i // per_arm] for i, s in enumerate(sample[arm][:n])] for arm in pop}
                    pb_raw = ev.p2bb(vals["raw"][a_name], vals["raw"][b_name])
                    pb_pred = ev.p2bb(vals["pred"][a_name], vals["pred"][b_name])
                    lead_raw = b_name if pb_raw > 0.5 else a_name
                    lead_pred = b_name if pb_pred > 0.5 else a_name
                    if "naive" not in stop and max(pb_raw, 1 - pb_raw) >= ev.THRESH:
                        stop["naive"] = (day, lead_raw)
                    if day == 14:
                        stop["wait14"] = (day, lead_raw)
                    if "guard" not in stop and max(pb_pred, 1 - pb_pred) >= ev.THRESH:
                        stop["guard"] = (day, lead_pred)
                    if day == MAX_DAYS:
                        stop.setdefault("naive", (day, lead_raw))
                        stop.setdefault("guard", (day, lead_pred))
                    if len(stop) == 3:
                        break
                for rule, (day, pick) in stop.items():
                    loss = 0.5 * traffic * gap * day + (traffic * gap * AFTER if pick != winner else 0)
                    r = res[rule]
                    r[0] += loss
                    r[1] += pick != winner
                    r[2] += day
            print(f"  scale x{scale}: placement traffic {traffic:.0f}/day")
            for rule, (loss, wrong, days) in res.items():
                print(f"    {rule:7s} expected loss ${loss / REPS:>10,.0f}   wrong ship {wrong / REPS:5.0%}   avg stop day {days / REPS:5.1f}")


if __name__ == "__main__":
    run()

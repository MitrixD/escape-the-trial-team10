"""Run the verdict agent on the synthetic test: one run per day, then a resampling grid.

Usage: python run_synth.py <repo with verdict_agent/> <dataset folder from make_test.py> [reps]
Needs the `verdict_agent` package from branch feature/verdict-agent (Python 3.11+).
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, sys.argv[1])

from verdict_agent.calibration import build_offline  # noqa: E402
from verdict_agent.guardrails import warnings_for  # noqa: E402
from verdict_agent.offline import _revenue, load_users, offline_test, run_offline, trial_days_from  # noqa: E402
from verdict_agent.verdict import build_verdict  # noqa: E402

DATA = Path(sys.argv[2])
REPS = int(sys.argv[3]) if len(sys.argv) > 3 else 100
OUT = Path(__file__).resolve().parent
TEST = "AI limit: annual upfront vs weekly trial"
H = 60

users = load_users(DATA, H)
truth = {}
for u in users.values():
    if u["test"] == TEST:
        truth.setdefault(u["arm"], []).append(_revenue(u, H))
truth = {k: sum(v) / len(v) for k, v in truth.items()}
winner = max(truth, key=truth.get)
print("truth 60d per user:", {k: round(v, 2) for k, v in truth.items()}, "winner:", winner)

print("\n== single runs, traffic 100/day per arm, seed 7 ==")
print(f"{'day':>3} {'verdict':>16} {'leader':>15} {'p2bb_raw':>8} {'p2bb_exp':>8} {'matur':>5} {'come_back':>10} {'stake$':>8}  A: recv/+tr/+ren   B: recv/+tr/+ren")
for day in (3, 7, 14, 21, 28, 45, 60):
    r = run_offline(DATA, TEST, day, 100, horizon=H)
    a, b = r["arms"]
    print(f"{day:>3} {r['verdict']:>16} {r['leader']:>15} {r['p2bb_raw']:>8.4f} {r['p2bb_expected']:>8.4f} {r['maturity']:>5.2f} {str(r['come_back_on']):>10} {r['money_at_stake_usd']:>8.0f}  "
          f"{a['revenue_received']:.2f}/{a['revenue_expected_trials']:.2f}/{a['revenue_expected_renewals']:.2f}   "
          f"{b['revenue_received']:.2f}/{b['revenue_expected_trials']:.2f}/{b['revenue_expected_renewals']:.2f}")
    if day in (7, 14, 28):
        (OUT / f"synth_day{day}.json").write_text(json.dumps(r, indent=2) + "\n")

print(f"\n== grid, {REPS} resamples per cell ==")
cal = build_offline(users, TEST, H)
trial_days = trial_days_from(users)
print(f"{'traffic':>7} {'day':>3} {'raw_wrong':>9} {'wrong_conf':>10} {'right_conf':>10} {'n.e.d.':>6} {'early':>6} {'tie':>6}  mean p2bb_raw(wrong arm)  mean p2bb_exp(true winner)")
for traffic in (100, 300):
    for day in (7, 14, 21, 28):
        rng = random.Random(f"synth|{day}|{traffic}")
        c = Counter()
        raw_wrong = exp_right = 0.0
        for _ in range(REPS):
            t = offline_test(users, TEST, day, traffic, seed=rng.randrange(2**31), horizon=H, cal=cal)
            r = build_verdict(t, cal, warnings=warnings_for(t), trial_days=trial_days, horizon=H)
            c[r["verdict"]] += 1
            if r["verdict"] == "confirmed":
                c["right" if r["leader"] == winner else "wrong"] += 1
            p_raw_wrong = r["p2bb_raw"] if r["leader"] != winner else 1 - r["p2bb_raw"]
            p_exp_right = r["p2bb_expected"] if r["leader"] == winner else 1 - r["p2bb_expected"]
            raw_wrong += p_raw_wrong
            exp_right += p_exp_right
            if p_raw_wrong >= 0.95:
                c["raw_wrong"] += 1

        def f(k):
            return f"{c[k] / REPS:6.0%}"

        print(f"{traffic:>7} {day:>3} {f('raw_wrong'):>9} {f('wrong'):>10} {f('right'):>10} {f('not_enough_data'):>6} {f('early'):>6} {f('tie'):>6}  {raw_wrong / REPS:24.3f}  {exp_right / REPS:26.3f}")

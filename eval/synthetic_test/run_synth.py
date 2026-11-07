"""Run the verdict agent on the synthetic test through replay bundles: one CLI run per day, then a resampling grid.

Usage: python eval/synthetic_test/run_synth.py <dataset folder from make_test.py> [reps]
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from eval.make_replay import make_replay, truth  # noqa: E402
from eval.verdict_eval import HORIZON, SYNTHETIC, score_cell  # noqa: E402

DATA = Path(sys.argv[1])
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 100
OUT = Path(__file__).resolve().parent
TRAFFIC = 100
SINGLE_DAYS = (3, 7, 14, 21, 28, 45, 60)
SAVED_DAYS = (7, 14, 28)
GRID_DAYS = (7, 14, 28, 60)
GRID_TRAFFIC = (100, 300)


def cli_verdict(day: int) -> dict:
    today = datetime.now(timezone.utc).date()
    with tempfile.TemporaryDirectory() as tmp:
        bundle = make_replay(DATA, SYNTHETIC, day, TRAFFIC, Path(tmp) / "bundle", start=today - timedelta(days=day))
        test_id = json.loads((bundle / "ab-tests_get.json").read_text())["ab_test_id"]
        env = {**os.environ, "PYTHONPATH": str(REPO)}
        done = subprocess.run([sys.executable, "-m", "verdict_agent.cli", test_id, "--replay", str(bundle)],
                              cwd=tmp, env=env, capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


values = truth(DATA, SYNTHETIC, HORIZON)
winner = max(values, key=values.get)
print("truth 60d per user:", {k: round(v, 2) for k, v in values.items()}, "winner:", winner)

print(f"\n== single CLI runs, traffic {TRAFFIC}/day per arm, seed 7, as of {datetime.now(timezone.utc).date()} ==")
print(f"{'day':>3} {'verdict':>16} {'reason':>15} {'leader':>15} {'p2bb_raw':>8} {'p2bb_exp':>8} {'matur':>5} "
      f"{'come_back':>10}  per arm: received/+trials/+renewals")
for day in SINGLE_DAYS:
    r = cli_verdict(day)
    arms = "   ".join(f"{a['title']} {a['revenue_received']:.2f}/{a['revenue_expected_trials']:.2f}/"
                      f"{a['revenue_expected_renewals']:.2f}" for a in r["arms"])
    print(f"{day:>3} {r['verdict']:>16} {str(r['reason']):>15} {r['leader']:>15} {r['p2bb_raw']:>8.4f} "
          f"{r['p2bb_expected']:>8.4f} {r['maturity']:>5.2f} {str(r['come_back_on']):>10}  {arms}")
    if day in SAVED_DAYS:
        (OUT / f"synth_day{day}.json").write_text(json.dumps(r, indent=2) + "\n")

print(f"\n== grid, {REPS} resamples per cell, run_live through replay bundles ==")
print(f"{'traffic':>7} {'day':>3} {'raw_wrong':>9} {'wrong_conf':>10} {'right_conf':>10} {'n.e.d.':>6} "
      f"{'keep_run':>8} {'tie':>6}")
for traffic in GRID_TRAFFIC:
    for day in GRID_DAYS:
        c = score_cell(DATA, SYNTHETIC, day, traffic, REPS)
        print(f"{traffic:>7} {day:>3} {c['raw_wrong']:>9.0%} {c['wrong_confirmed']:>10.0%} "
              f"{c['right_confirmed']:>10.0%} {c['not_enough_data']:>6.0%} {c['keep_running']:>8.0%} {c['tie']:>6.0%}")

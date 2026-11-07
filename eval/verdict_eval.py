"""Eval of the verdict agent on the offline Lumen dataset.

Grid: each historical test x decision day x traffic per arm, REPS resampled runs per cell.
Truth: net revenue per user at HORIZON days over the full arm population.
Noise: segment check on random attributes that carry no effect.

Usage: python eval/verdict_eval.py [DATASET] [--reps N]
"""
import argparse
import os
import random
import sys
import time
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict_agent.calibration import build_offline
from verdict_agent.offline import _revenue, load_users, offline_test
from verdict_agent.segments import check_segments
from verdict_agent.verdict import build_verdict

HORIZON = 60
DAYS = [1, 3, 7, 14, 21, 28]
TRAFFIC = [30, 100]
REPS = 150
SEED = 7
VERDICTS = ["not_enough_data", "confirmed", "early", "tie"]
NOISE_TEST = "Settings: upgrade vs lifetime anchor"
NOISE_RUNS = 20
NOISE_ATTRS = 20
NOISE_DAY = 14
NOISE_TRAFFIC = 100

_users: dict = {}


def truth(users: dict, test_name: str, horizon: int = HORIZON) -> dict[str, float]:
    sums: dict[str, list[float]] = {}
    for u in users.values():
        if u["test"] == test_name:
            sums.setdefault(u["arm"], []).append(_revenue(u, horizon))
    return {arm: sum(v) / len(v) for arm, v in sorted(sums.items())}


def _raw_wrong(result: dict, winner: str) -> bool:
    p = result["p2bb_raw"]
    return p >= 0.95 if result["leader"] != winner else p <= 0.05


def eval_cell(users, test_name, cal, winner, day, traffic, reps, seed=SEED) -> dict:
    rng = random.Random(f"{seed}|{test_name}|{day}|{traffic}")
    counts = Counter()
    for _ in range(reps):
        test = offline_test(users, test_name, day, traffic, seed=rng.randrange(2**31), horizon=HORIZON, cal=cal)
        result = build_verdict(test, cal, horizon=HORIZON)
        verdict = result["verdict"]
        counts[verdict] += 1
        if verdict == "confirmed":
            counts["right_confirmed" if result["leader"] == winner else "wrong_confirmed"] += 1
        if _raw_wrong(result, winner):
            counts["raw_wrong"] += 1
            if verdict in ("early", "tie"):
                counts["early_when_raw_wrong"] += 1
    row = {"test": test_name, "day": day, "traffic": traffic, "reps": reps}
    for key in ["wrong_confirmed", "right_confirmed", "raw_wrong", "early_when_raw_wrong", *VERDICTS]:
        row[key] = counts[key] / reps
    return row


def _init(path):
    _users.update(load_users(Path(path), HORIZON))


def _test_job(args):
    test_name, reps = args
    cal = build_offline(_users, test_name, HORIZON)
    t = truth(_users, test_name)
    winner = max(t, key=t.get)
    return [eval_cell(_users, test_name, cal, winner, d, tr, reps) for tr in TRAFFIC for d in DAYS]


def noise_eval(users, runs=NOISE_RUNS, attrs=NOISE_ATTRS, seed=SEED) -> tuple[int, int]:
    rng = random.Random(seed)
    cal = build_offline(users, NOISE_TEST, HORIZON)
    dims = [f"noise_{i}" for i in range(attrs)]
    checked = found = 0
    for _ in range(runs):
        test = offline_test(users, NOISE_TEST, NOISE_DAY, NOISE_TRAFFIC, seed=rng.randrange(2**31), horizon=HORIZON, cal=cal)
        rows = {
            arm: [({d: rng.choice("ab") for d in dims}, value) for _, value in arm_rows]
            for arm, arm_rows in test.segment_rows.items()
        }
        n, hits = check_segments(rows, dims)
        checked += n
        found += len(hits)
    return checked, found


def _pct(x: float) -> str:
    return f"{x:5.0%}"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default=os.environ.get("VERDICT_DATASET"))
    parser.add_argument("--reps", type=int, default=REPS)
    args = parser.parse_args(argv)
    if not args.dataset:
        parser.error("pass DATASET or set VERDICT_DATASET")
    started = time.time()
    users = load_users(Path(args.dataset), HORIZON)
    tests = sorted({u["test"] for u in users.values() if u["test"]})
    print(f"verdict eval: horizon={HORIZON}d reps={args.reps} seed={SEED} days={DAYS} traffic/arm={TRAFFIC}")
    print("subsamples are drawn with replacement from ~900-1,800 users per arm: confidence is inflated")
    with get_context("fork").Pool(len(tests), initializer=_init, initargs=(args.dataset,)) as pool:
        results = pool.map(_test_job, [(t, args.reps) for t in tests])
    for test_name, rows in zip(tests, results):
        t = truth(users, test_name)
        winner = max(t, key=t.get)
        print(f"\n=== {test_name}")
        print("  truth ARPU@60d: " + ", ".join(f"{k}=${v:.2f}" for k, v in t.items()) + f"  winner={winner}")
        print("  traffic day | wrong_conf right_conf raw_wrong early_raw_wrong | not_enough confirmed early   tie")
        for r in rows:
            print(
                f"  {r['traffic']:>7} {r['day']:>3} | {_pct(r['wrong_confirmed'])}      {_pct(r['right_confirmed'])}"
                f"     {_pct(r['raw_wrong'])}       {_pct(r['early_when_raw_wrong'])}      |"
                f"      {_pct(r['not_enough_data'])}     {_pct(r['confirmed'])} {_pct(r['early'])} {_pct(r['tie'])}"
            )
    checked, found = noise_eval(users)
    print(f"\nnoise: {NOISE_RUNS} runs x {NOISE_ATTRS} random attributes on {NOISE_TEST}, day {NOISE_DAY}, "
          f"{NOISE_TRAFFIC}/day/arm: segments checked={checked} found={found}")
    print(f"elapsed {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()

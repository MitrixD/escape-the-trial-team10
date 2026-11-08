"""Score the Verdict Agent against 60-day truth on replayed A/B tests from the offline dataset.

Each cell (test x day x traffic) replays `reps` resampled runs of the test through make_replay
bundles and run_live, and compares the verdict with the truth winner: the arm with the higher
60-day net revenue per user over its full population.

Usage: python eval/verdict_eval.py <dataset> [--synthetic <dataset from make_test.py>] [--reps N]
"""
import argparse
import json
import random
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.make_replay import DATA_END, make_replay, truth  # noqa: E402
from verdict_agent.live import run_live  # noqa: E402

TESTS = ["Main: 3 plans vs lifetime anchor (NA)", "Onboarding: annual trial vs weekly first",
         "Settings: upgrade vs lifetime anchor"]
SYNTHETIC = "AI limit: annual upfront vs weekly trial"
DAYS = [1, 3, 7, 14, 21, 28]
TRAFFIC = [30, 100]
REPS = 150
SEED = 7
HORIZON = 60
CONFIDENT = 0.95
WAIT_RULE_DAY = 14
VERDICTS = ["not_enough_data", "keep_running", "confirmed", "tie"]
SHIPS = ["wrong_ship", "right_ship", "money_ship", "money_wrong_ship"]
SHARES = ["wrong_confirmed", "right_confirmed", "raw_wrong", *VERDICTS, *SHIPS]


def score_cell(dataset: Path, test: str, day: int, traffic: int, reps: int = REPS, seed: int = SEED,
               arrival: str = "uniform") -> dict:
    values = truth(dataset, test, HORIZON)
    winner = max(values, key=values.get)
    rng = random.Random(f"{seed}|{test}|{day}|{traffic}")
    counts = Counter()
    with tempfile.TemporaryDirectory() as scratch:
        no_env = Path(scratch) / "no.env"
        for _ in range(reps):
            with tempfile.TemporaryDirectory(dir=scratch) as tmp:
                bundle = make_replay(dataset, test, day, traffic, Path(tmp), seed=rng.randrange(2**31),
                                     arrival=arrival)
                test_id = json.loads((bundle / "ab-tests_get.json").read_text())["ab_test_id"]
                r = run_live(test_id, today=DATA_END.date(), horizon=HORIZON, replay=bundle, env_path=no_env)
            right = r["leader"] == winner
            counts[r["verdict"]] += 1
            if r["verdict"] == "confirmed":
                counts["right_confirmed" if right else "wrong_confirmed"] += 1
            if r["next_action"] == "ship_leader":
                counts["right_ship" if right else "wrong_ship"] += 1
                if r["next_action_basis"] == "money":
                    counts["money_ship"] += 1
                    counts["money_wrong_ship"] += not right
            p_raw = r["p2bb_raw"]
            if (not right and p_raw >= CONFIDENT) or (right and p_raw <= 1 - CONFIDENT):
                counts["raw_wrong"] += 1
    return {"test": test, "day": day, "traffic": traffic, "reps": reps, "winner": winner,
            **{k: counts[k] / reps for k in SHARES}}


def first_safe_day(cells: list[dict]) -> int | None:
    for c in sorted(cells, key=lambda c: c["day"]):
        if c["right_confirmed"] >= 0.5 and c["wrong_confirmed"] <= 0.05 + 1e-9:
            return c["day"]
    return None


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _vs_wait_rule(day: int | None) -> str:
    if day is None:
        return f"not by day {DAYS[-1]}"
    if day < WAIT_RULE_DAY:
        return f"{WAIT_RULE_DAY - day} days earlier"
    return "same day" if day == WAIT_RULE_DAY else f"{day - WAIT_RULE_DAY} days later"


def print_tables(tests: list[tuple[Path, str]], cells: list[dict]) -> None:
    for dataset, test in tests:
        values = truth(dataset, test, HORIZON)
        mine = [c for c in cells if c["test"] == test]
        print(f"\n### {test}\n")
        print("Truth, 60-day net revenue per user: "
              + ", ".join(f"`{arm}` ${v:.2f}" for arm, v in values.items())
              + f"; winner `{mine[0]['winner']}`.\n")
        print("| Traffic/day | Day | wrong_confirmed | right_confirmed | raw_wrong "
              "| not_enough_data | keep_running | confirmed | tie | wrong_ship | right_ship | money_ship "
              "| money_wrong_ship |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c in mine:
            print(f"| {c['traffic']} | {c['day']} | " + " | ".join(_pct(c[k]) for k in SHARES) + " |")
    print("\n### First safe day vs the 14-day rule\n")
    print("First day with right_confirmed ≥ 50% and wrong_confirmed ≤ 5%.\n")
    print("| Test | Traffic/day | First safe day | vs day 14 |")
    print("|---|---|---|---|")
    for _, test in tests:
        for traffic in TRAFFIC:
            day = first_safe_day([c for c in cells if c["test"] == test and c["traffic"] == traffic])
            print(f"| {test} | {traffic} | {day if day is not None else '—'} | {_vs_wait_rule(day)} |")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--synthetic", type=Path, help="dataset folder written by eval/synthetic_test/make_test.py")
    parser.add_argument("--reps", type=int, default=REPS)
    parser.add_argument("--json", type=Path, help="also write every cell to this JSON file")
    args = parser.parse_args(argv)
    tests = [(args.dataset, t) for t in TESTS]
    if args.synthetic:
        tests.append((args.synthetic, SYNTHETIC))
    started = time.monotonic()
    cells = []
    for dataset, test in tests:
        for traffic in TRAFFIC:
            for day in DAYS:
                cells.append(score_cell(dataset, test, day, traffic, args.reps))
                print(f"done {test} {traffic}/day day {day}", file=sys.stderr, flush=True)
    minutes = (time.monotonic() - started) / 60
    print(f"horizon={HORIZON}d reps={args.reps} seed={SEED} days={DAYS} traffic={TRAFFIC} "
          f"confident>={CONFIDENT:.0%} runtime={minutes:.1f} min")
    print_tables(tests, cells)
    if args.json:
        args.json.write_text(json.dumps(cells, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

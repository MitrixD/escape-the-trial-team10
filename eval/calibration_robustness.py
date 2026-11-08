"""How wrong can the calibration be before the verdict confirms the wrong variant?

Runs the replay grid of eval/verdict_eval.py with the calibration's trial->paid conversion and renewal curves
scaled by 0.8 and 1.2 independently (four corners and the centre). The product code is unchanged: only this
script wraps live_calibration. From Maxim's validation strategy, section 4.4.

Usage: python eval/calibration_robustness.py <dataset> [--synthetic <dataset from make_test.py>] [--reps N]
"""
import argparse
import contextlib
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval import verdict_eval  # noqa: E402
from verdict_agent import live  # noqa: E402
from verdict_agent.model import Calibration  # noqa: E402

CORNERS = [(1.0, 1.0), (0.8, 0.8), (0.8, 1.2), (1.2, 0.8), (1.2, 1.2)]
DAYS = [7, 14, 28]
TRAFFIC = 100
TESTS = ["Settings: upgrade vs lifetime anchor"]


def scale_calibration(cal: Calibration, conversion: float, renewals: float) -> Calibration:
    return dataclasses.replace(
        cal,
        trial_to_paid={p: c * conversion for p, c in cal.trial_to_paid.items()},
        renewal_value={p: [v * renewals for v in curve] for p, curve in cal.renewal_value.items()},
        app_trial_to_paid=None if cal.app_trial_to_paid is None else cal.app_trial_to_paid * conversion,
        app_renewal_value=None if cal.app_renewal_value is None else [v * renewals for v in cal.app_renewal_value],
    )


@contextlib.contextmanager
def scaled_live_calibration(conversion: float, renewals: float):
    original = live.live_calibration

    def scaled(*args, **kwargs):
        return scale_calibration(original(*args, **kwargs), conversion, renewals)

    live.live_calibration = scaled
    try:
        yield
    finally:
        live.live_calibration = original


def score_corner(dataset: Path, test: str, day: int, traffic: int, conversion: float, renewals: float,
                 reps: int = verdict_eval.REPS) -> dict:
    with scaled_live_calibration(conversion, renewals):
        cell = verdict_eval.score_cell(dataset, test, day, traffic, reps)
    return {**cell, "conversion": conversion, "renewals": renewals}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--synthetic", type=Path, help="dataset folder written by eval/synthetic_test/make_test.py")
    parser.add_argument("--reps", type=int, default=verdict_eval.REPS)
    args = parser.parse_args(argv)
    tests = [(args.dataset, t) for t in TESTS]
    if args.synthetic:
        tests.append((args.synthetic, verdict_eval.SYNTHETIC))
    started = time.monotonic()
    rows = []
    for dataset, test in tests:
        for day in DAYS:
            for conversion, renewals in CORNERS:
                rows.append(score_corner(dataset, test, day, TRAFFIC, conversion, renewals, args.reps))
                print(f"done {test} day {day} x{conversion}/{renewals}", file=sys.stderr, flush=True)
    print(f"reps={args.reps} seed={verdict_eval.SEED} traffic={TRAFFIC}/day per variant "
          f"runtime={(time.monotonic() - started) / 60:.1f} min\n")
    print("| Test | Day | Conversion × | Renewals × | wrong_confirmed | right_confirmed | keep_running | wrong_ship |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['test']} | {r['day']} | {r['conversion']} | {r['renewals']} | {r['wrong_confirmed']:.0%} "
              f"| {r['right_confirmed']:.0%} | {r['keep_running']:.0%} | {r['wrong_ship']:.0%} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())

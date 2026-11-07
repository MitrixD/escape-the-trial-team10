import importlib.util
import math
import sys
from pathlib import Path

import pytest

from verdict_agent.stats import diff_ci, p2bb, users_needed

SAMPLE_A = [0.0, 0.0, 4.99, 0.0, 9.99, 0.0, 0.0, 29.99, 0.0, 4.99, 0.0, 0.0]
SAMPLE_B = [0.0, 9.99, 0.0, 19.99, 0.0, 0.0, 49.99, 0.0, 9.99, 0.0, 0.0, 14.99]


def load_spike():
    path = Path(__file__).resolve().parent.parent / "eval" / "ab_verdict_eval.py"
    spec = importlib.util.spec_from_file_location("ab_verdict_eval_spike", path)
    module = importlib.util.module_from_spec(spec)
    saved = sys.argv
    sys.argv = [str(path)]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    return module


def test_p2bb_matches_spike():
    spike = load_spike()
    assert p2bb(SAMPLE_A, SAMPLE_B) == spike.p2bb(SAMPLE_A, SAMPLE_B)
    assert p2bb(SAMPLE_B, SAMPLE_A) == spike.p2bb(SAMPLE_B, SAMPLE_A)


def test_p2bb_degenerate_cases():
    assert p2bb([1.0], [2.0, 3.0]) == 0.5
    assert p2bb([], []) == 0.5
    assert p2bb([1.0, 1.0], [1.0, 1.0]) == 0.5
    assert p2bb([1.0, 1.0], [2.0, 2.0]) == 1.0
    assert p2bb([2.0, 2.0], [1.0, 1.0]) == 0.0


def test_diff_ci_welch_interval():
    xa, xb = [1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0]
    se = math.sqrt((5 / 3) / 4 + (20 / 3) / 4)
    low, high = diff_ci(xa, xb)
    assert low == pytest.approx(3.5 - 1.959964 * se, abs=1e-5)
    assert high == pytest.approx(3.5 + 1.959964 * se, abs=1e-5)


def test_diff_ci_level_widens():
    narrow = diff_ci(SAMPLE_A, SAMPLE_B, level=0.8)
    wide = diff_ci(SAMPLE_A, SAMPLE_B, level=0.99)
    assert wide[0] < narrow[0] < narrow[1] < wide[1]


def test_diff_ci_too_few_users():
    assert diff_ci([1.0], [1.0, 2.0]) == (-math.inf, math.inf)
    assert diff_ci([1.0, 2.0], []) == (-math.inf, math.inf)


def test_users_needed_hand_computed():
    assert users_needed(1.0, 2.0) == 63


def test_users_needed_edges():
    assert users_needed(1.0, 0.0) == 1
    assert users_needed(0.5, 2.0) > users_needed(1.0, 2.0)
    assert users_needed(1.0, 2.0, power=0.9) > users_needed(1.0, 2.0)
    for delta, sd in [(0.0, 1.0), (-1.0, 1.0), (1.0, -1.0)]:
        with pytest.raises(ValueError):
            users_needed(delta, sd)

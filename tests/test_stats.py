import pytest

from tests.helpers import load_spike
from verdict_agent.stats import bonferroni, diff_in_diff_p, p2bb, two_prop_p, welch_p

spike = load_spike()


def test_p2bb_matches_spike():
    xa, xb = [0, 0, 10, 0], [10, 10, 0, 10]
    assert p2bb(xa, xb) == pytest.approx(spike.p2bb(xa, xb))


def test_p2bb_degenerate():
    assert p2bb([1], [2]) == 0.5


def test_two_prop_equal():
    assert two_prop_p(10, 100, 10, 100) == pytest.approx(1.0)


def test_two_prop_different():
    assert two_prop_p(5, 100, 30, 100) < 0.001


def test_two_prop_zero_variance():
    assert two_prop_p(0, 100, 0, 100) == 1.0


def test_welch_different_and_equal():
    assert welch_p([0, 1, 0, 1] * 10, [5, 6, 5, 6] * 10) < 0.001
    assert welch_p([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_welch_degenerate():
    assert welch_p([1], [2, 3]) == 1.0


def test_diff_in_diff():
    seg_a, seg_b = [0, 1] * 30, [5, 6] * 30
    rest_a, rest_b = [0, 1] * 30, [0, 1] * 30
    assert diff_in_diff_p(seg_a, seg_b, rest_a, rest_b) < 0.001
    assert diff_in_diff_p(seg_a, seg_b, seg_a, seg_b) == pytest.approx(1.0)


def test_bonferroni_caps_at_one():
    assert bonferroni([0.03, 0.5]) == pytest.approx([0.06, 1.0])

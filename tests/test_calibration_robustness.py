from pathlib import Path

import pytest

from eval.calibration_robustness import CORNERS, scale_calibration, scaled_live_calibration
from tests.helpers import make_cal, step_curve


def test_scaling_multiplies_conversion_and_curves():
    cal = make_cal({"p": step_curve(15.0)}, conv=0.5)
    cal.app_trial_to_paid, cal.app_renewal_value = 0.4, [1.0, 2.0]
    out = scale_calibration(cal, conversion=0.8, renewals=1.2)
    assert out.trial_to_paid["p"] == pytest.approx(0.4)
    assert out.app_trial_to_paid == pytest.approx(0.32)
    assert out.renewal_value["p"][-1] == pytest.approx(25.0 * 1.2)
    assert out.app_renewal_value == pytest.approx([1.2, 2.4])
    assert out.trial_days == cal.trial_days and out.source == cal.source
    assert cal.trial_to_paid["p"] == 0.5


def test_expected_revenue_scales_with_both_factors():
    cal = make_cal({"p": step_curve(15.0)}, conv=0.5)
    base = cal.expected("trial", "p", 3, 60)
    assert scale_calibration(cal, 0.8, 1.2).expected("trial", "p", 3, 60) == pytest.approx(base * 0.96)
    assert scale_calibration(cal, 1.0, 1.2).expected("active", "p", 3, 60) == pytest.approx(
        cal.expected("active", "p", 3, 60) * 1.2)


def test_grid_has_four_corners_and_the_centre():
    assert sorted(CORNERS) == [(0.8, 0.8), (0.8, 1.2), (1.0, 1.0), (1.2, 0.8), (1.2, 1.2)]


def test_live_calibration_is_restored_after_the_context():
    from verdict_agent import live
    original = live.live_calibration
    with scaled_live_calibration(0.8, 1.2):
        assert live.live_calibration is not original
    assert live.live_calibration is original


@pytest.mark.dataset
def test_one_cell_runs(dataset_path):
    from eval.calibration_robustness import score_corner
    cell = score_corner(Path(dataset_path), "Settings: upgrade vs lifetime anchor", 14, 100, 0.8, 1.2, reps=2)
    assert {"wrong_confirmed", "right_confirmed", "conversion", "renewals"} <= set(cell)

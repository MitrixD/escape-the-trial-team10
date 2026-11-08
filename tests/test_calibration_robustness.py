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


def test_one_product_can_be_scaled_alone():
    cal = make_cal({"p": step_curve(15.0), "q": step_curve(15.0)}, conv=0.5)
    out = scale_calibration(cal, 1.0, 1.0, products={"q": 1.3})
    assert out.renewal_value["p"] == cal.renewal_value["p"]
    assert out.renewal_value["q"][-1] == pytest.approx(cal.renewal_value["q"][-1] * 1.3)


def test_adverse_cells_cover_product_skew_and_front_loaded_arrival():
    from eval.calibration_robustness import ADVERSE
    assert {c["name"] for c in ADVERSE} == {"weekly renewals x1.3", "front-loaded arrival",
                                             "weekly renewals x1.3 and front-loaded arrival"}


@pytest.mark.dataset
def test_front_loaded_bundle_puts_every_user_in_the_first_three_days(dataset_path, tmp_path):
    import json
    from eval.make_replay import make_replay
    out = make_replay(Path(dataset_path), "Settings: upgrade vs lifetime anchor", 14, 20, tmp_path / "f",
                      arrival="front")
    rows = json.loads((out / "ab-tests_metrics_total.json").read_text())["data"]["metrics"]
    assert [r["users"] for r in rows] == [280, 280]
    with pytest.raises(ValueError, match="arrival"):
        make_replay(Path(dataset_path), "Settings: upgrade vs lifetime anchor", 14, 20, tmp_path / "g",
                    arrival="sideways")

from pathlib import Path

import pytest

from eval.verdict_eval import SHARES, VERDICTS, first_safe_day, score_cell

pytestmark = pytest.mark.dataset

SETTINGS = "Settings: upgrade vs lifetime anchor"


def test_one_cell_with_two_reps_has_every_share(dataset_path):
    cell = score_cell(Path(dataset_path), SETTINGS, day=14, traffic=30, reps=2)
    assert {"test", "day", "traffic", "reps", "winner", *SHARES} <= set(cell)
    assert cell["reps"] == 2
    assert cell["winner"] == "main_lifetime"
    assert sum(cell[v] for v in VERDICTS) == pytest.approx(1.0)
    assert cell["confirmed"] == pytest.approx(cell["right_confirmed"] + cell["wrong_confirmed"])
    assert all(0 <= cell[k] <= 1 for k in SHARES)


def test_first_safe_day_needs_half_right_and_at_most_five_percent_wrong():
    cells = [
        {"day": 1, "right_confirmed": 0.6, "wrong_confirmed": 0.1},
        {"day": 3, "right_confirmed": 0.4, "wrong_confirmed": 0.0},
        {"day": 7, "right_confirmed": 0.5, "wrong_confirmed": 0.05},
    ]
    assert first_safe_day(cells) == 7
    assert first_safe_day(cells[:2]) is None

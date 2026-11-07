import importlib.util
from pathlib import Path

import pytest

from verdict_agent.calibration import build_offline
from verdict_agent.offline import load_users

SETTINGS = "Settings: upgrade vs lifetime anchor"
EVAL = Path(__file__).resolve().parent.parent / "eval" / "verdict_eval.py"


def _load_eval():
    spec = importlib.util.spec_from_file_location("verdict_eval", EVAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.dataset
def test_eval_cell_row_keys(dataset_path):
    ev = _load_eval()
    users = load_users(dataset_path, ev.HORIZON)
    cal = build_offline(users, SETTINGS, ev.HORIZON)
    truth = ev.truth(users, SETTINGS)
    row = ev.eval_cell(users, SETTINGS, cal, max(truth, key=truth.get), day=1, traffic=30, reps=2)
    assert set(row) == {
        "test", "day", "traffic", "reps", "wrong_confirmed", "right_confirmed", "raw_wrong",
        "early_when_raw_wrong", "not_enough_data", "confirmed", "early", "tie",
    }
    assert row["reps"] == 2
    assert sum(row[v] for v in ev.VERDICTS) == pytest.approx(1.0)

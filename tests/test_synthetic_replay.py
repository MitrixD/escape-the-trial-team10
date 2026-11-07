import json
from pathlib import Path

import pytest

from schema_check import assert_valid
from verdict_agent.live import run_live

SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic"
DAYS = (14,)


def bundle(day):
    return SYNTHETIC / f"day{day}"


def ab_test_id(day):
    return json.loads((bundle(day) / "ab-tests_get.json").read_text())["ab_test_id"]


@pytest.mark.parametrize("day", DAYS)
def test_synthetic_bundle_is_small_and_gives_a_valid_verdict(day):
    assert sum(p.stat().st_size for p in bundle(day).iterdir()) < 300_000
    out = run_live(ab_test_id(day), replay=bundle(day))
    assert_valid(out)
    assert [a["users"] for a in out["arms"]] == [100 * day] * 2


def test_day_14_confirms_weekly_trial_while_raw_p2bb_picks_annual():
    out = run_live(ab_test_id(14), replay=bundle(14))
    assert out["verdict"] == "confirmed"
    assert out["leader"] == "weekly_trial"
    assert out["p2bb_raw"] <= 0.05

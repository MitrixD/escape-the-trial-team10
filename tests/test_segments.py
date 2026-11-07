import random

import pytest

from tests.helpers import offline_rows
from verdict_agent.segments import check_segments

DIMS = ["platform", "acquisition_channel", "onboarding_goal", "push_opt_in"]


@pytest.mark.dataset
def test_settings_ios_rejected(dataset_path, spike_users):
    rows = offline_rows(dataset_path, spike_users, "Settings: upgrade vs lifetime anchor")
    assert len(rows) == 2
    checked, found = check_segments(rows)
    assert checked > 0 and found == []


def test_random_segments_rejected():
    rng = random.Random(2026)
    total = 0
    for _ in range(20):
        rows = {}
        for arm in ("A", "B"):
            rows[arm] = [
                ({f"attr{j}": rng.choice(["x", "y"]) for j in range(20)}, rng.expovariate(1 / 3) * rng.choice([0, 0, 1]))
                for _ in range(600)
            ]
        checked, found = check_segments(rows, dimensions=[f"attr{j}" for j in range(20)])
        assert checked == 40
        total += len(found)
    assert total <= 1


def test_real_effect_found():
    rng = random.Random(1)
    rows = {"A": [], "B": []}
    for arm in rows:
        for _ in range(1000):
            seg = rng.choice(["ios", "android"])
            lift = 5.0 if (arm == "B" and seg == "ios") else 0.0
            rows[arm].append(({"platform": seg}, rng.gauss(10, 2) + lift))
    checked, found = check_segments(rows)
    assert checked == 2
    assert {f["value"] for f in found} <= {"ios", "android"}
    ios = [f for f in found if f["value"] == "ios"][0]
    assert ios["dimension"] == "platform" and ios["lift"] == pytest.approx(5.0, abs=0.5)
    assert ios["p_adjusted"] < 0.05


def test_small_values_skipped():
    rows = {
        "A": [({"platform": "ios"}, 1.0)] * 99 + [({"platform": "android"}, 1.0)] * 500,
        "B": [({"platform": "ios"}, 1.0)] * 500 + [({"platform": "android"}, 1.0)] * 500,
    }
    checked, found = check_segments(rows)
    assert checked == 0
    assert all(f["value"] != "ios" for f in found)

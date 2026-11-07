import pytest

from tests.helpers import load_spike
from verdict_agent.calibration import Calibration, build_offline, load, save

EXCLUDED = "Settings: upgrade vs lifetime anchor"
spike = load_spike()


@pytest.mark.dataset
def test_offline_calibration_equals_spike(spike_users):
    ours = build_offline(spike_users, EXCLUDED, 60)
    table, fallback = spike.calibrate([u for u in spike_users.values() if u["test"] != EXCLUDED])
    assert table
    for (st, age), v in list(table.items())[:200]:
        assert ours.expected(st[0], st[1], age) == pytest.approx(v)
    assert ours.source == "offline"


def test_unknown_product_falls_back():
    cal = Calibration({("trial", "weekly", 1): 5.0}, {("trial", "weekly"): 4.0}, {"trial": 3.0}, source="test")
    assert cal.expected("trial", "unknown_product", 1) == 3.0
    assert cal.expected("trial", "weekly", 1) == 5.0
    assert cal.expected("trial", "weekly", 9) == 4.0
    assert cal.expected("ended", "x", 1) == 0.0


def test_save_load_roundtrip(tmp_path):
    cal = Calibration({("trial", "weekly", 1): 5.0}, {("trial", "weekly"): 4.0}, {"trial": 3.0}, source="test")
    path = tmp_path / "cal.json"
    save(cal, path)
    back = load(path)
    assert back.source == "test"
    assert back.expected("trial", "weekly", 1) == 5.0
    assert back.expected("trial", "weekly", 9) == 4.0
    assert back.expected("trial", "other", 1) == 3.0

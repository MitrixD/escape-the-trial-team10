import pytest

from tests.helpers import groups_from_sample, load_spike, make_arm, spike_sample
from verdict_agent.calibration import Calibration, build_offline
from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.model import Group

EXCLUDED = "Settings: upgrade vs lifetime anchor"


def test_pending_trials_raise_expected():
    cal = Calibration({}, {("trial", "annual_trial"): 20.0}, {}, source="test")
    arm = make_arm([Group("trial", "annual_trial", 0.5, 66, 0.0), Group("none", "-", 0.5, 188, 0.0)])
    est = estimate(arm, cal)
    assert est.received == 0 and est.from_trials == pytest.approx(66 * 20 / 254)
    assert est.total == pytest.approx(66 * 20 / 254)


def test_active_and_received_split():
    cal = Calibration({}, {("active", "m"): 5.0, ("ended", "m"): 1.0}, {}, source="test")
    arm = make_arm([Group("active", "m", 3.5, 10, 2.0), Group("ended", "m", 3.5, 10, 4.0)])
    est = estimate(arm, cal)
    assert est.received == pytest.approx(3.0)
    assert est.from_renewals == pytest.approx(2.5)
    assert est.from_trials == 0
    assert est.total == pytest.approx(3.0 + 2.5 + 0.5)


def test_empty_arm():
    cal = Calibration({}, {}, {}, source="test")
    arm = make_arm([])
    est = estimate(arm, cal)
    assert (est.received, est.from_trials, est.from_renewals, est.total) == (0.0, 0.0, 0.0, 0.0)
    assert pseudo_values(arm, cal) == []


def test_pseudo_values_length_and_mean():
    cal = Calibration({}, {("trial", "p"): 7.0}, {"none": 0.0}, source="test")
    arm = make_arm([Group("trial", "p", 1.5, 3, 1.0), Group("none", "-", 1.5, 5, 0.5)])
    values = pseudo_values(arm, cal)
    assert len(values) == arm.users == 8
    assert sum(values) / len(values) == pytest.approx(estimate(arm, cal).total)
    assert values.count(8.0) == 3 and values.count(0.5) == 5


@pytest.mark.dataset
def test_groups_mean_equals_per_user_mean(spike_users):
    spike = load_spike()
    pop = [u for u in spike_users.values() if u["test"] == EXCLUDED and u["arm"]]
    arm_name = sorted({u["arm"] for u in pop})[0]
    pop = [u for u in pop if u["arm"] == arm_name]
    sample, ages = spike_sample(spike, pop, 100, 14)
    history = [u for u in spike_users.values() if u["test"] != EXCLUDED]
    table, fallback = spike.calibrate(history)
    per_user = sum(spike.predict(u, a, table, fallback) for u, a in zip(sample, ages)) / len(sample)
    cal = build_offline(spike_users, EXCLUDED, 60)
    arm = make_arm(groups_from_sample(spike, sample, ages))
    assert arm.users == len(sample)
    assert estimate(arm, cal).total == pytest.approx(per_user, abs=0.01)

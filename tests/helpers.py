import importlib.util
import pathlib
import sys


def load_spike():
    path = pathlib.Path(__file__).resolve().parent.parent / "eval" / "ab_verdict_eval.py"
    spec = importlib.util.spec_from_file_location("spike", path)
    module = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, ["spike"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    module.DATA = "unused"
    module.HORIZON = 60
    return module


def make_arm(groups, title="arm"):
    from verdict_agent.model import Arm

    return Arm(title, list(groups), 0, 0, 0, 0, 0.0, {})


def spike_sample(spike, pop, traffic, day, seed=7):
    import random

    random.seed(seed)
    n = traffic * day
    sample = [random.choice(pop) for _ in range(n)]
    ages = [day - (i // traffic) - random.random() for i in range(n)]
    return sample, ages


def groups_from_sample(spike, sample, ages):
    from collections import defaultdict

    from verdict_agent.model import Group

    acc = defaultdict(list)
    for u, age in zip(sample, ages):
        status, product = spike.state(u, age)
        acc[(status, product, int(age))].append(spike.rev(u, age))
    return [Group(s, p, a, len(v), sum(v) / len(v)) for (s, p, a), v in acc.items()]


STARTED_ON = (2026, 10, 1)
AS_OF = (2026, 10, 11)
PAYER_VALUE = 10.0


def make_test(arms, goal="Find which onboarding offer maximises 60-day revenue per install", users_per_day=50.0):
    from datetime import date

    from verdict_agent.model import TestData

    return TestData(
        "test-1", "Fake test", goal, "placement-1", date(*STARTED_ON), date(*AS_OF),
        users_per_day, list(arms), "offline", None,
    )


def payer_arm(title, n, k, received, events, product="m", status="active"):
    from verdict_agent.model import Arm, Group

    groups = []
    if k:
        groups.append(Group(status, product, 5.0, k, received))
    if n - k:
        groups.append(Group("none", "-", 5.0, n - k, 0.0))
    return Arm(title, groups, events, 0, k, 0, received * k, {})


def closest_k(target, n, k_a, k_range):
    from verdict_agent.stats import p2bb

    base = [1.0] * k_a + [0.0] * (n - k_a)
    return min(k_range, key=lambda k: abs(p2bb(base, [1.0] * k + [0.0] * (n - k)) - target))


def fake(p2bb=0.7, maturity=0.5, events=None, users=None, equal=False):
    from verdict_agent.calibration import Calibration

    events = events or [100, 100]
    users = users or [1000, 1000]
    received = maturity * PAYER_VALUE
    cal = Calibration({}, {}, {"active": PAYER_VALUE - received, "none": 0.0}, "test")
    k_a = users[0] // 5
    if equal:
        k_b = k_a
    elif users == [1000, 1000]:
        k_b = closest_k(p2bb, 1000, k_a, range(k_a + 1, 400))
    else:
        k_b = users[1] // 4
    arms = [
        payer_arm("A", users[0], k_a, received, events[0]),
        payer_arm("B", users[1], k_b, received, events[1]),
    ]
    return make_test(arms), cal

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

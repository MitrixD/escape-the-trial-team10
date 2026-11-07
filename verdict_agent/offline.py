"""Offline mode: verdicts on the offline Lumen dataset as of a given test day. Trial-cancel timing uses the dataset's final renew_status/renew_status_changed_at, so reactivations are not visible."""
import csv
import gzip
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from verdict_agent.calibration import Calibration, build_offline
from verdict_agent.guardrails import warnings_for
from verdict_agent.model import Arm, Group, TestData
from verdict_agent.segments import DIMENSIONS, check_segments
from verdict_agent.verdict import DEFAULT_HORIZON, build_verdict, check_horizon

DATA_END = datetime.fromisoformat("2026-11-03T00:00:00+00:00")
AS_OF = date(2026, 11, 3)
TRIAL_CANCEL_WINDOW_DAYS = 1.0
_CACHE: dict[tuple[str, int], dict[str, dict]] = {}
_TRIAL_DAYS: dict[tuple[str, int], dict[str, int]] = {}


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _age(s: str, install: datetime) -> float:
    return (_ts(s) - install).total_seconds() / 86400


def load_users(path: Path, horizon: int) -> dict[str, dict]:
    with gzip.open(f"{path}/users.csv.gz", "rt") as fh:
        rows = list(csv.DictReader(fh))
    tx = defaultdict(list)
    with gzip.open(f"{path}/transactions.csv.gz", "rt") as fh:
        for t in csv.DictReader(fh):
            tx[t["user_id"]].append(t)
    out = {}
    for u in rows:
        inst = _ts(u["install_at"])
        if (DATA_END - inst).days < horizon:
            continue
        ev, subs, txs = [], [], []
        for t in tx[u["user_id"]]:
            start = _age(t["purchased_at"], inst)
            price = float(t["price_usd"] or 0)
            ev.append((start, price))
            refund = _age(t["refunded_at"], inst) if t["refunded_at"] else None
            if refund is not None:
                ev.append((refund, -price))
            expires = _age(t["expires_at"], inst) if t["expires_at"] else 1e9
            trial = t["offer"] == "free_trial"
            subs.append((start, expires, t["product"], trial))
            renew_off = None
            if t["renew_status"] == "false" and t["renew_status_changed_at"]:
                renew_off = _age(t["renew_status_changed_at"], inst)
            txs.append({
                "start": start, "expires": expires, "product": t["product"], "is_trial": trial,
                "price_usd": price, "refund": refund, "renew_off": renew_off,
            })
        out[u["user_id"]] = {
            "test": u["ab_test"],
            "arm": u["flow"],
            "ev": ev,
            "subs": sorted(subs),
            "attrs": {k: u[k] for k in DIMENSIONS},
            "tx": txs,
        }
    return out


def _revenue(user: dict, age: float) -> float:
    return sum(p for a, p in user["ev"] if a <= age)


def _state(user: dict, age: float) -> tuple[str, str]:
    current = [s for s in user["subs"] if s[0] <= age]
    if not current:
        return "none", "-"
    _, exp, product, trial = current[-1]
    if exp > age:
        return ("trial" if trial else "active"), product
    return "ended", product


def trial_days_from(users: dict[str, dict]) -> dict[str, int]:
    lengths = defaultdict(list)
    for u in users.values():
        for t in u["tx"]:
            if t["is_trial"] and t["expires"] < 1e9:
                lengths[t["product"]].append(t["expires"] - t["start"])
    return {p: round(statistics.median(v)) for p, v in sorted(lengths.items())}


def _arm(title: str, sample: list[dict], ages: list[float], cal: Calibration):
    acc = defaultdict(list)
    purchases = trials = paid_users = refunds = 0
    revenue = 0.0
    cancels = defaultdict(lambda: [0, 0])
    rows = []
    for u, age in zip(sample, ages):
        status, product = _state(u, age)
        received = _revenue(u, age)
        acc[(status, product, int(age))].append(received)
        revenue += received
        rows.append((u["attrs"], received + cal.expected(status, product, age)))
        started = [t for t in u["tx"] if t["start"] <= age]
        trials += any(t["is_trial"] for t in started)
        paid = any(t["price_usd"] > 0 for t in started)
        purchases += paid
        paid_users += paid
        refunds += sum(1 for t in u["tx"] if t["refund"] is not None and t["refund"] <= age)
        trial_products = {}
        for t in started:
            if t["is_trial"]:
                off = t["renew_off"]
                quick = off is not None and off <= age and off - t["start"] <= TRIAL_CANCEL_WINDOW_DAYS
                trial_products[t["product"]] = trial_products.get(t["product"], False) or quick
        for product_name, cancelled in trial_products.items():
            cancels[product_name][0] += cancelled
            cancels[product_name][1] += 1
    groups = [Group(s, p, a, len(v), sum(v) / len(v)) for (s, p, a), v in acc.items()]
    arm = Arm(
        title, groups, purchases, trials, paid_users, refunds, revenue,
        {p: (c, n) for p, (c, n) in sorted(cancels.items())},
    )
    return arm, rows


def _population(users: dict[str, dict], test_name: str) -> dict[str, list[dict]]:
    pop = defaultdict(list)
    for u in users.values():
        if u["test"] == test_name:
            pop[u["arm"]].append(u)
    if not pop:
        available = sorted({u["test"] for u in users.values() if u["test"]})
        raise ValueError(f"unknown offline test {test_name!r}; available: {', '.join(available)}")
    return pop


def offline_test(
    users: dict[str, dict],
    test_name: str,
    day: int,
    traffic: int,
    seed: int = 7,
    horizon: int = 60,
    cal: Calibration | None = None,
) -> TestData:
    pop = _population(users, test_name)
    if cal is None:
        cal = build_offline(users, test_name, horizon)
    return _sampled_test(pop, test_name, day, traffic, seed, horizon, cal)


def _sampled_test(pop, test_name, day, traffic, seed, horizon, cal) -> TestData:
    rng = random.Random(seed)
    arms, segment_rows = [], {}
    for name in sorted(pop):
        n = traffic * day
        sample = [rng.choice(pop[name]) for _ in range(n)]
        ages = [day - (i // traffic) - rng.random() for i in range(n)]
        arm, rows = _arm(name, sample, ages, cal)
        arms.append(arm)
        segment_rows[name] = rows
    return TestData(
        ab_test_id=test_name,
        title=test_name,
        goal=f"{horizon}-day revenue per user",
        placement_id=None,
        started_on=AS_OF - timedelta(days=day),
        as_of=AS_OF,
        users_per_day=traffic * len(arms),
        arms=arms,
        source="offline",
        segment_rows=segment_rows,
    )


def _cached_users(path: Path, horizon: int) -> tuple[dict[str, dict], dict[str, int]]:
    key = (str(Path(path).resolve()), horizon)
    if key not in _CACHE:
        _CACHE[key] = load_users(path, horizon)
        _TRIAL_DAYS[key] = trial_days_from(_CACHE[key])
    return _CACHE[key], _TRIAL_DAYS[key]


def run_offline(
    path: Path, test_name: str, day: int, traffic: int, seed: int = 7, horizon: int | None = None,
) -> dict:
    check_horizon(horizon)
    if day < 1:
        raise ValueError("day must be at least 1")
    if traffic < 1:
        raise ValueError("traffic must be at least 1")
    resolved = DEFAULT_HORIZON if horizon is None else horizon
    users, trial_days = _cached_users(path, resolved)
    pop = _population(users, test_name)
    cal = build_offline(users, test_name, resolved)
    test = _sampled_test(pop, test_name, day, traffic, seed, resolved, cal)
    return build_verdict(
        test,
        cal,
        warnings=warnings_for(test),
        segments=check_segments(test.segment_rows),
        trial_days=trial_days,
        horizon=horizon,
    )

"""Turn one A/B test of the offline dataset into an Adapty-shaped replay bundle for day N.

Usage: python eval/make_replay.py <dataset> "<test name>" <day> <traffic> <out_dir>
"""
import csv
import gzip
import json
import random
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

DATA_END = datetime(2026, 11, 3, tzinfo=timezone.utc)
MIN_HISTORY_DAYS = 60
RENEWAL_DAYS = [0, 3, 7, 14, 28, 31, 61, 92, 183]
STORES = {"iOS": "app_store", "Android": "play_store"}
EPS = 1e-9
NEVER = 1e9


@dataclass(frozen=True)
class Tx:
    product: str
    store: str
    store_product_id: str
    start: float
    expires: float
    price: float
    trial: bool
    refund: float | None


@dataclass(frozen=True)
class User:
    test: str
    arm: str
    placement: str
    history_days: float
    tx: tuple[Tx, ...]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _age(s: str, install: datetime) -> float:
    return (_ts(s) - install).total_seconds() / 86400


@lru_cache(maxsize=4)
def _load(dataset_dir: str) -> tuple[User, ...]:
    with gzip.open(f"{dataset_dir}/users.csv.gz", "rt") as fh:
        rows = list(csv.DictReader(fh))
    platform = {u["user_id"]: u["platform"] for u in rows}
    install = {u["user_id"]: _ts(u["install_at"]) for u in rows}
    tx = defaultdict(list)
    with gzip.open(f"{dataset_dir}/transactions.csv.gz", "rt") as fh:
        for t in csv.DictReader(fh):
            inst = install[t["user_id"]]
            tx[t["user_id"]].append(Tx(
                product=t["product"],
                store=STORES.get(platform[t["user_id"]], "app_store"),
                store_product_id=t["store_product_id"],
                start=_age(t["purchased_at"], inst),
                expires=_age(t["expires_at"], inst) if t["expires_at"] else NEVER,
                price=float(t["price_usd"] or 0),
                trial=t["offer"] == "free_trial",
                refund=_age(t["refunded_at"], inst) if t["refunded_at"] else None,
            ))
    return tuple(
        User(u["ab_test"], u["flow"], u["placement"], (DATA_END - install[u["user_id"]]).total_seconds() / 86400,
             tuple(sorted(tx[u["user_id"]], key=lambda t: t.start)))
        for u in rows
    )


def rev(user: User, age: float) -> float:
    total = 0.0
    for t in user.tx:
        if t.start <= age:
            total += t.price
        if t.refund is not None and t.refund <= age:
            total -= t.price
    return total


def _population(users, test_name: str, min_days: int) -> dict[str, list[User]]:
    pop = defaultdict(list)
    for u in users:
        if u.test == test_name and int(u.history_days) >= min_days:
            pop[u.arm].append(u)
    if not pop:
        available = sorted({u.test for u in users if u.test})
        raise ValueError(f"unknown offline test {test_name!r}; available: {', '.join(available)}")
    return dict(sorted(pop.items()))


def truth(dataset_dir: Path, test_name: str, horizon: int = 60) -> dict[str, float]:
    pop = _population(_load(str(dataset_dir)), test_name, horizon)
    return {arm: sum(rev(u, horizon) for u in v) / len(v) for arm, v in pop.items()}


@dataclass
class Seen:
    product: str | None
    trial: bool
    paid: bool
    trial_finished: bool
    purchases: int
    refunds: int
    revenue: float


def _observe(user: User, age: float) -> Seen:
    started = [t for t in user.tx if t.start <= age]
    refunds = sum(1 for t in user.tx if t.refund is not None and t.refund <= age)
    if not started:
        return Seen(None, False, False, False, 0, refunds, rev(user, age))
    first = started[0]
    return Seen(
        product=first.product,
        trial=first.trial,
        paid=any(t.price > 0 for t in started),
        trial_finished=first.trial and first.expires <= age,
        purchases=sum(1 for t in started if t.price > 0),
        refunds=refunds,
        revenue=rev(user, age),
    )


def _pct(a: float, b: float) -> float:
    return a / b * 100 if b else 0


def _metrics_row(arm: str, weight: int, seen: list[Seen]) -> dict:
    users = len(seen)
    revenue = round(sum(s.revenue for s in seen), 2)
    trials = sum(s.trial for s in seen)
    finished = sum(s.trial_finished for s in seen)
    trials_paid = sum(s.trial and s.paid for s in seen)
    paid = sum(s.paid for s in seen)
    subscribers = sum(s.product is not None for s in seen)
    purchases = sum(s.purchases for s in seen)
    refunds = sum(s.refunds for s in seen)
    return {
        "views": users, "unique_profiles_views": users, "total_completions": 0, "total_uniq_completions": 0,
        "from_start_conversion": 0, "revenue": revenue, "proceeds": 0, "net_revenue": 0,
        "purchases": purchases, "trials": trials, "unique_subscribers": subscribers,
        "unique_paid_subscribers": paid, "arppu": revenue / paid if paid else 0,
        "arpu": revenue / users if users else 0, "conversion_rate_purchases": _pct(purchases, users),
        "conversion_rate_trials": _pct(trials, users), "trials_cancelled": 0, "refunds": refunds,
        "arpas": revenue / subscribers if subscribers else 0, "apppu": 0, "appas": 0,
        "conversion_rate_refunds": _pct(refunds, purchases), "conversion_rate_purchases_by_users": _pct(paid, users),
        "conversion_rate_trials_by_users": _pct(trials, users), "conversion_rate_trial_paid": _pct(trials_paid, finished),
        "trials_finished": finished, "trials_paid": trials_paid, "users": users, "installs": users,
        "title": arm, "variation_id": arm, "flow_id": arm, "weight": weight,
        "active_trials_rate": (trials - finished) / trials if trials else 0,
        "probability": 0, "low_boundary": 0, "average_per_1000": 0, "upper_boundary": 0, "p_value": 0,
    }


def _steps(users: int, trials: int, paid: int) -> list[dict]:
    raw = [(-2, "Install", users), (-1, "Paywall displayed", users),
           (0, "Trial" if trials else "0 period", trials), (1, "Paid" if paid else "1 period", paid)]
    out = []
    for i, (x, title, value) in enumerate(raw):
        following = raw[i + 1][2] if i + 1 < len(raw) else 0
        out.append({
            "x": x, "title": title, "value": value, "value_relative": _pct(value, users),
            "relative_changes": _pct(following, value),
            "following_changes": {"title": "Drop off", "value": max(0, value - following),
                                  "value_relative": _pct(max(0, value - following), value)},
            "churn_reason_title": "", "churn_reasons": [], "parts": [],
        })
    return out


def _funnel(arm: str, placement: str, start: date, as_of: date, seen: list[Seen]) -> dict:
    users = len(seen)
    by_product: dict[str, list[int]] = {}
    for s in seen:
        if s.product is None:
            continue
        cell = by_product.setdefault(s.product, [0, 0, 0])
        if s.trial:
            cell[0] += 1
            cell[1] += s.paid
        else:
            cell[2] += s.paid
    segments = []
    for product, (trials, converted, direct) in sorted(by_product.items()):
        if trials and direct:
            raise ValueError(f"arm {arm}: product {product} has both trial and direct buyers; "
                             "one funnel row cannot hold both")
        segments.append({"key": product, "title": product, "is_total": False, "value": users,
                         "values": _steps(users, trials, converted if trials else direct)})
    trials = sum(c[0] for c in by_product.values())
    paid = sum(c[1] + c[2] for c in by_product.values())
    total = {"key": None, "title": "Total", "is_total": True, "value": users, "values": _steps(users, trials, paid)}
    return {
        "data": {"value": users, "segments": [total, *segments]},
        "meta": {"query": {"timezone": "UTC", "filters": {"date": [start.isoformat(), as_of.isoformat()],
                                                          "placement_id": [placement], "flow_id": [arm]},
                           "segmentation": "store_product_id"}},
    }


def _period(txs: list[Tx]) -> str:
    lengths = [t.expires - t.start for t in txs if t.price > 0 and not t.trial]
    if not lengths or statistics.median(lengths) >= NEVER / 2:
        return "lifetime"
    days = statistics.median(lengths)
    return "weekly" if days <= 10 else "monthly" if days <= 40 else "annual"


def _products(users) -> dict:
    txs = defaultdict(list)
    for u in users:
        for t in u.tx:
            txs[t.product].append(t)
    rows = []
    for product, items in sorted(txs.items()):
        vendors = {}
        for store in ("app_store", "play_store"):
            ids = sorted({t.store_product_id for t in items if t.store == store})
            if ids:
                vendors[store] = {"id": None, "product_id": ids[0], "base_plan_id": None, "store_status": None}
        rows.append({"id": product, "title": product, "period": _period(items), "access_level_id": None,
                     "price_usd": 0, "vendor_products": vendors, "offers_count": 0})
    return {"data": rows, "meta": {"pagination": {"page": 1, "pages": 1, "count": len(rows)}}}


def _window(users) -> tuple[date, date]:
    first = min(DATA_END - timedelta(days=u.history_days) for u in users)
    return first.date(), (DATA_END - timedelta(days=1)).date()


def _conversion(history: list[User], window: tuple[date, date]) -> dict:
    days = [(window[0] + timedelta(days=i)) for i in range((window[1] - window[0]).days + 1)]
    daily: dict[str, dict[date, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    for u in history:
        installed = DATA_END - timedelta(days=u.history_days)
        for t in u.tx:
            if not t.trial:
                continue
            cell = daily[t.product][(installed + timedelta(days=t.start)).date()]
            if t.expires > u.history_days:
                cell[2] += 1
                continue
            cell[0] += 1
            cell[1] += any(o.product == t.product and o.price > 0 and o.start >= t.start for o in u.tx)

    def segment(key, title, cells):
        values = []
        for d in days:
            f, to, unfinished = cells.get(d, [0, 0, 0])
            values.append({"x": f"{d.isoformat()}T00:00:00.000000+0000", "value": _pct(to, f), "value_from": f,
                           "value_to": to, "value_from_unfinished": unfinished, "has_unfinished": unfinished > 0})
        f = sum(v["value_from"] for v in values)
        to = sum(v["value_to"] for v in values)
        return {"key": key, "title": title, "is_total": key is None, "value": _pct(to, f),
                "value_from": f, "value_to": to, "values": values}

    total_cells: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0])
    for cells in daily.values():
        for d, c in cells.items():
            total_cells[d] = [a + b for a, b in zip(total_cells[d], c)]
    total = segment(None, "Total", total_cells)
    segments = [segment(p, p, cells) for p, cells in sorted(daily.items())]
    return {
        "data": {"value": total["value"], "value_from": total["value_from"], "value_to": total["value_to"],
                 "compare": None, "segments": [total, *segments]},
        "meta": {"query": {"timezone": "UTC", "conversion_id": "trial-paid",
                           "filters": {"date": [window[0].isoformat(), window[1].isoformat()]},
                           "segmentation": "store_product_id", "period_unit": "day"}},
    }


def _ltv_units(history: list[User]) -> dict[str, list[tuple[float, list[tuple[float, float]]]]]:
    units = defaultdict(list)
    for u in history:
        by_product = defaultdict(list)
        for t in u.tx:
            by_product[t.product].append(t)
        for product, txs in sorted(by_product.items()):
            if not any(t.price > 0 for t in txs):
                continue
            start = min(t.start for t in txs)
            events = [(t.start - start, t.price) for t in txs]
            events += [(t.refund - start, -t.price) for t in txs if t.refund is not None]
            units[product].append((u.history_days - start, events))
    return units


def _ltv_segment(key, title, units) -> dict:
    values = []
    for x in RENEWAL_DAYS:
        seen = [events for observed, events in units if observed >= x]
        if seen:
            per_payer = sum(sum(p for a, p in ev if a <= x + EPS) for ev in seen) / len(seen)
            values.append({"x": x, "value": round(per_payer, 2)})
    return {"key": key, "title": title, "is_total": key is None, "value": values[-1]["value"] if values else 0,
            "cohort_size": len(units), "values": values}


def _ltv(history: list[User], window: tuple[date, date]) -> dict:
    units = _ltv_units(history)
    total = _ltv_segment(None, "Total", [unit for p in sorted(units) for unit in units[p]])
    segments = [_ltv_segment(p, p, units[p]) for p in sorted(units)]
    return {
        "data": {"value": total["value"], "segments": [total, *segments]},
        "meta": {"query": {"timezone": "UTC", "filters": {"date": [window[0].isoformat(), window[1].isoformat()]},
                           "segmentation": "store_product_id", "revenue_basis": "gross",
                           "period_type": "days", "renewal_days": RENEWAL_DAYS}},
    }


def _cohort(window: tuple[date, date]) -> dict:
    return {"data": {"value": 0, "segments": []},
            "meta": {"query": {"timezone": "UTC", "filters": {"date": [window[0].isoformat(), window[1].isoformat()]},
                               "period_unit": "month", "revenue_basis": "gross", "period_type": "renewals"}}}


def _write(out_dir: Path, name: str, body: dict) -> None:
    (out_dir / name).write_text(json.dumps(body, indent=2) + "\n")


def make_replay(dataset_dir: Path, test_name: str, day: int, traffic: int, out_dir: Path,
                seed: int = 7, start: date | None = None) -> Path:
    start = start or (DATA_END.date() - timedelta(days=day))
    as_of = start + timedelta(days=day)
    users = _load(str(dataset_dir))
    pop = _population(users, test_name, MIN_HISTORY_DAYS)
    rng = random.Random(seed)
    observed: dict[str, list[Seen]] = {}
    for arm, members in pop.items():
        n = traffic * day
        sample = [rng.choice(members) for _ in range(n)]
        ages = [day - (i // traffic) - rng.random() for i in range(n)]
        observed[arm] = [_observe(u, a) for u, a in zip(sample, ages)]

    test_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"verdict-eval:{test_name}"))
    placement = Counter(u.placement for v in pop.values() for u in v).most_common(1)[0][0]
    started_at = f"{start.isoformat()}T00:00:00Z"
    goal = "Find which arm maximises revenue per user"
    weight = 100 // len(pop)
    flows = [{"flow_id": arm, "flow_name": arm, "weight": weight, "title": arm, "variation_id": arm} for arm in pop]
    history = [u for u in users if u.test != test_name]
    window = _window(users)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir, "auth_whoami.json", {"company": "<redacted>", "matched_expected_company": True})
    _write(out_dir, "ab-tests_get.json", {
        "ab_test_id": test_id, "title": test_name, "type": "flow", "state": "live",
        "placement": {"placement_id": placement, "title": placement}, "segment_ids": [], "priority": 0,
        "started_at": started_at, "stopped_at": None, "goal": goal, "paywalls": [], "flows": flows,
    })
    _write(out_dir, "ab-tests_metrics_total.json", {"data": {
        "metrics": [_metrics_row(arm, weight, seen) for arm, seen in observed.items()],
        "ab_test": {"ab_test_id": test_id, "title": test_name, "goal": goal,
                    "paywalls_group": {"paywalls_group_id": test_id, "title": test_name},
                    "vars": {}, "created_at": started_at},
        "state": "live", "started_at": started_at, "stopped_at": None, "active_trials_rate": 0,
    }})
    _write(out_dir, "products_list.json", _products(users))
    for arm, seen in observed.items():
        _write(out_dir, f"analytics_funnel_{arm}.json", _funnel(arm, placement, start, as_of, seen))
    _write(out_dir, "analytics_conversion_trial-paid.json", _conversion(history, window))
    _write(out_dir, "analytics_cohort.json", _cohort(window))
    _write(out_dir, "analytics_ltv.json", _ltv(history, window))
    return out_dir


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    dataset, test_name, day, traffic, out_dir = argv
    print(make_replay(Path(dataset), test_name, int(day), int(traffic), Path(out_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

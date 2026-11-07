import json
from collections import defaultdict
from pathlib import Path


class Calibration:
    def __init__(self, table, by_product, by_status, source):
        self.table = table
        self.by_product = by_product
        self.by_status = by_status
        self.source = source

    def expected(self, status: str, product: str, age_days: float) -> float:
        key = (status, product, int(age_days))
        if key in self.table:
            return self.table[key]
        if (status, product) in self.by_product:
            return self.by_product[(status, product)]
        return self.by_status.get(status, 0.0)


def _revenue(user, age):
    return sum(p for a, p in user["ev"] if a <= age)


def _state(user, age):
    current = [s for s in user["subs"] if s[0] <= age]
    if not current:
        return "none", "-"
    _, exp, product, trial = current[-1]
    if exp > age:
        return ("trial" if trial else "active"), product
    return "ended", product


def build_offline(users: dict, exclude_test: str, horizon: int) -> Calibration:
    acc = defaultdict(lambda: [0.0, 0])
    for u in users.values():
        if u["test"] == exclude_test:
            continue
        final = _revenue(u, horizon)
        for age in range(horizon + 1):
            status, product = _state(u, age)
            cell = acc[(status, product, age)]
            cell[0] += final - _revenue(u, age)
            cell[1] += 1
    table = {k: s / n for k, (s, n) in acc.items()}
    by_product_acc = defaultdict(lambda: [0.0, 0])
    by_status_acc = defaultdict(lambda: [0.0, 0])
    for (status, product, _), (s, n) in acc.items():
        by_product_acc[(status, product)][0] += s
        by_product_acc[(status, product)][1] += n
        by_status_acc[status][0] += s
        by_status_acc[status][1] += n
    by_product = {k: s / n for k, (s, n) in by_product_acc.items()}
    by_status = {k: s / n for k, (s, n) in by_status_acc.items()}
    return Calibration(table, by_product, by_status, "offline")


def save(cal: Calibration, path) -> None:
    data = {
        "source": cal.source,
        "table": {"|".join((s, p, str(a))): v for (s, p, a), v in cal.table.items()},
        "by_product": {"|".join(k): v for k, v in cal.by_product.items()},
        "by_status": cal.by_status,
    }
    Path(path).write_text(json.dumps(data))


def load(path) -> Calibration:
    data = json.loads(Path(path).read_text())
    table = {}
    for k, v in data["table"].items():
        status, product, age = k.split("|")
        table[(status, product, int(age))] = v
    by_product = {tuple(k.split("|", 1)): v for k, v in data["by_product"].items()}
    return Calibration(table, by_product, data["by_status"], data["source"])

from dataclasses import dataclass
from datetime import date

DEFAULT_TRIAL_DAYS = 7


@dataclass(frozen=True)
class Group:
    status: str
    product: str
    age_days: float
    n: int
    received: float


@dataclass
class Arm:
    title: str
    groups: list[Group]
    purchases: int
    trials: int
    paid_users: int
    revenue_received: float

    @property
    def users(self) -> int:
        return sum(g.n for g in self.groups)


@dataclass
class TestData:
    __test__ = False

    ab_test_id: str
    title: str
    placement_id: str | None
    started_on: date
    as_of: date
    users_per_day: float
    arms: list[Arm]


def _value_at(curve: list[float], days: float) -> float:
    if days <= 0:
        return curve[0]
    last = len(curve) - 1
    if days >= last:
        return curve[last]
    lo = int(days)
    return curve[lo] + (curve[lo + 1] - curve[lo]) * (days - lo)


@dataclass
class Calibration:
    trial_to_paid: dict[str, float]
    renewal_value: dict[str, list[float]]
    trial_days: dict[str, int]
    app_trial_to_paid: float | None
    app_renewal_value: list[float] | None
    source: str

    def _curve(self, product: str) -> list[float] | None:
        return self.renewal_value.get(product) or self.app_renewal_value or None

    def _conversion(self, product: str) -> float | None:
        c = self.trial_to_paid.get(product)
        return self.app_trial_to_paid if c is None else c

    def expected(self, status: str, product: str, age_days: float, horizon: float) -> float:
        if status not in ("trial", "active") or age_days >= horizon:
            return 0.0
        curve = self._curve(product)
        if not curve:
            return 0.0
        gain = _value_at(curve, horizon) - _value_at(curve, age_days)
        if status == "trial":
            return max(gain, 0.0)
        conv = self._conversion(product)
        if self.trial_days.get(product, DEFAULT_TRIAL_DAYS) > 0 and conv:
            return gain / conv
        return gain

    def source_for(self, product: str) -> str:
        if self.renewal_value.get(product):
            return "product"
        if self.app_renewal_value:
            return "app"
        return "none"

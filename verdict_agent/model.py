from dataclasses import dataclass, field
from datetime import date

DEFAULT_TRIAL_DAYS = 7
PERIOD_DAYS = {"weekly": 7, "monthly": 30, "two_months": 61, "trimonthly": 92, "semiannual": 183,
               "annual": 365, "lifetime": float("inf")}


class VerdictError(ValueError):
    pass


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
    weight: int | None = None

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
    running_days: int | None = None
    stopped: bool = False


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
    periods: dict[str, str] = field(default_factory=dict)

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
        if status == "active":
            return min(gain, 0.0) if self._no_renewal_within(product, horizon) else gain
        conv = self._conversion(product)
        return max(conv * gain, 0.0) if conv else 0.0

    def _no_renewal_within(self, product: str, horizon: float) -> bool:
        return PERIOD_DAYS.get(self.periods.get(product), 0) >= horizon

    def trial_outcome(self, product: str, age_days: float, horizon: float) -> tuple[float, float]:
        """Conversion rate and the gain of a converting trial user; (0, 0) when nothing is expected."""
        if age_days >= horizon:
            return 0.0, 0.0
        curve, conv = self._curve(product), self._conversion(product)
        if not curve or not conv:
            return 0.0, 0.0
        return conv, max(_value_at(curve, horizon) - _value_at(curve, age_days), 0.0)

    def has_trial_rate(self, product: str) -> bool:
        return self._conversion(product) is not None

    def source_for(self, product: str) -> str:
        if self.renewal_value.get(product):
            return "product"
        if self.app_renewal_value:
            return "app"
        return "none"

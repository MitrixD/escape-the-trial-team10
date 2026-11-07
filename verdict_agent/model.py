from dataclasses import dataclass
from datetime import date


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
    refunds: int
    revenue_received: float
    trial_cancels: dict[str, tuple[int, int]]

    @property
    def users(self) -> int:
        return sum(g.n for g in self.groups)


@dataclass
class TestData:
    __test__ = False

    ab_test_id: str
    title: str
    goal: str
    placement_id: str | None
    started_on: date
    as_of: date
    users_per_day: float
    arms: list[Arm]
    source: str
    segment_rows: dict[str, list[tuple[dict[str, str], float]]] | None

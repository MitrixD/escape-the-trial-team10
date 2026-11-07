from dataclasses import dataclass, field

from verdict_agent.calibration import Calibration
from verdict_agent.model import Arm


@dataclass
class ArmEstimate:
    received: float
    from_trials: float
    from_renewals: float
    _other: float = field(default=0.0, init=False, repr=False, compare=False)

    @property
    def total(self) -> float:
        return self.received + self.from_trials + self.from_renewals + self._other


def estimate(arm: Arm, cal: Calibration) -> ArmEstimate:
    users = arm.users
    if users == 0:
        return ArmEstimate(0.0, 0.0, 0.0)
    received = trials = renewals = other = 0.0
    for g in arm.groups:
        received += g.n * g.received
        expected = g.n * cal.expected(g.status, g.product, g.age_days)
        if g.status == "trial":
            trials += expected
        elif g.status == "active":
            renewals += expected
        else:
            other += expected
    est = ArmEstimate(received / users, trials / users, renewals / users)
    est._other = other / users
    return est


def pseudo_values(arm: Arm, cal: Calibration) -> list[float]:
    values: list[float] = []
    for g in arm.groups:
        values.extend([g.received + cal.expected(g.status, g.product, g.age_days)] * g.n)
    return values

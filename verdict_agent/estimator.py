from dataclasses import dataclass

from verdict_agent.model import Arm, Calibration


@dataclass(frozen=True)
class ArmEstimate:
    received: float
    from_trials: float
    from_renewals: float

    @property
    def total(self) -> float:
        return self.received + self.from_trials + self.from_renewals


def estimate(arm: Arm, cal: Calibration, horizon: float) -> ArmEstimate:
    users = arm.users
    if users == 0:
        return ArmEstimate(0.0, 0.0, 0.0)
    received = trials = renewals = 0.0
    for g in arm.groups:
        received += g.n * g.received
        future = g.n * cal.expected(g.status, g.product, g.age_days, horizon)
        if g.status == "trial":
            trials += future
        elif g.status == "active":
            renewals += future
    return ArmEstimate(received / users, trials / users, renewals / users)


def pseudo_values(arm: Arm, cal: Calibration, horizon: float) -> list[float]:
    values: list[float] = []
    for g in arm.groups:
        values.extend([g.received + cal.expected(g.status, g.product, g.age_days, horizon)] * g.n)
    return values

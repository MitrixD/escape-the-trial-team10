# Spec Delta

## MODIFIED Requirements

### Requirement: Expected revenue per arm
The system SHALL estimate each arm's revenue per user at the test horizon as received revenue plus expected revenue from pending trials plus expected revenue from future renewals. Expectations SHALL come from a calibration table built from the app's own Adapty analytics (trial→paid conversion and renewal revenue per product), applied to per-arm counts by user state (none, trial, active, ended), product and age. The trial and renewal parts SHALL be reported separately per arm. A product whose catalog period (annual, lifetime) is not shorter than the horizon SHALL get no expected renewals for its active users, only expected refunds (a falling curve). For the probability, the users of a trial group SHALL be represented as converting or not, so that their values keep the group's expected mean exactly and carry the spread of the conversion outcome.

#### Scenario: Pending trials count toward expected revenue
- **WHEN** an arm has $0 received and 66 users in an active trial of a product whose calibrated trial→paid conversion and renewal value are positive
- **THEN** the arm's expected revenue is greater than $0 and `revenue_expected_trials` is greater than 0

#### Scenario: Up-front arm has no future revenue
- **WHEN** an arm's paying users all hold a product with no renewals inside the horizon
- **THEN** `revenue_expected_renewals` for that arm is 0 or negative (expected refunds only)

#### Scenario: Annual product gets no renewals before a year
- **WHEN** the horizon is 60 days, an active user holds an annual product and the calibrated curve of that product rises after day 0
- **THEN** that user's expected future revenue is 0 or negative

#### Scenario: Counts and per-user data agree
- **WHEN** the estimate is computed from per-arm state counts and from the same users one by one with the same calibration
- **THEN** both give the same expected revenue per user within $0.01

#### Scenario: Trial outcome spread lowers confidence
- **WHEN** arm A has 40 of 400 users who paid $40 up front and arm B has 120 of 400 users in a trial with conversion 0.3 and a $60 gain
- **THEN** `p2bb_expected` for B is below 0.95 and the verdict is not `confirmed`

### Requirement: Horizon
The horizon in days SHALL be a parameter of the call. When omitted it SHALL be 60. A horizon below 1 SHALL be rejected with an error. A horizon shorter than the test's age in days SHALL be rejected with an error naming both, because received revenue would then cover more days than the horizon. The test goal SHALL NOT be parsed for a horizon.

#### Scenario: Caller horizon
- **WHEN** the caller passes a horizon of 30 days
- **THEN** `horizon_days` is 30 and the expected revenue is computed to day 30

#### Scenario: Default horizon
- **WHEN** no horizon is passed
- **THEN** `horizon_days` is 60

#### Scenario: Horizon below one day
- **WHEN** the caller passes a horizon of 0
- **THEN** the system returns an error and no verdict

#### Scenario: Horizon shorter than the test
- **WHEN** the test is 14 days old and the caller passes a horizon of 7 days
- **THEN** the system returns an error naming 7 and 14 and no verdict

### Requirement: Verdict rules
The system SHALL return exactly one verdict, checked in this order: `not_enough_data` (an arm below 30 purchases plus trials, or no calibration; no calibration includes an arm with users in trial when neither their product nor the app has a trial→paid rate); `confirmed` (expected P2BB of the leader ≥ 0.95); `tie` (maturity ≥ 0.80 and the 95% interval of |Δ expected revenue per user| lies below the MDE, 5% of the leader's value); otherwise `keep_running`. Maturity is received divided by expected revenue across arms.

#### Scenario: Too little data
- **WHEN** one arm has 12 purchases and trials combined
- **THEN** the verdict is `not_enough_data` with reason `min_events`

#### Scenario: Trials without any conversion rate
- **WHEN** every arm has at least 30 events, an arm has users in trial, and the calibration has a renewal curve but no trial→paid rate for their product or the app
- **THEN** the verdict is `not_enough_data` with reason `no_calibration`

#### Scenario: Confident before maturity
- **WHEN** P2BB on expected revenue is 0.97 and maturity is 0.40
- **THEN** the verdict is `confirmed`, not `keep_running`

#### Scenario: Immature and unsure
- **WHEN** P2BB on expected revenue is 0.70 and maturity is 0.50
- **THEN** the verdict is `keep_running` with reason `pending_revenue`

#### Scenario: Mature, unsure and underpowered
- **WHEN** P2BB on expected revenue is 0.84, maturity is 0.83 and the interval of the difference still includes values above the minimum detectable effect
- **THEN** the verdict is `keep_running` with reason `underpowered`

#### Scenario: Mature and provably equal
- **WHEN** maturity is 0.90 and the whole 95% interval of the absolute difference lies below 5% of the leader's expected revenue per user
- **THEN** the verdict is `tie`

### Requirement: Come-back date for keep running
For `keep_running`, `come_back_on` SHALL be the later of two dates: test start + the longest trial length among the arms' products + 30 days; and today + the days until the smaller of the two compared arms reaches the size needed to detect the current difference at 95%, at that arm's own observed daily traffic. It SHALL be capped at start + horizon and never be before today. When this gives the judging day itself while the horizon has not been reached, `come_back_on` SHALL be 7 days later, still capped at start + horizon, so the reader always gets a day to come back.

#### Scenario: Date for pending revenue
- **WHEN** a test with 7-day trials started on 7 Nov and the verdict is `keep_running` with reason `pending_revenue`
- **THEN** `come_back_on` is on or after 14 Dec and not after start + horizon

#### Scenario: Unequal weights
- **WHEN** a 90/10 test is `keep_running` with reason `underpowered` and the 10% arm lacks users
- **THEN** the days to come back are counted at the 10% arm's daily traffic, not at half of the test's traffic

#### Scenario: Nothing new to wait for before the horizon
- **WHEN** the verdict is `keep_running` on day 40 of a 60-day horizon and both dates of the rule fall before the judging day
- **THEN** `come_back_on` is 7 days after the judging day

### Requirement: Raw P2BB shown next to expected P2BB
The system SHALL report both P2BB on received revenue (`p2bb_raw`) and P2BB on expected revenue (`p2bb_expected`) for the leader, so the reader sees when they disagree. With two arms both are the probability that the leader beats the other arm. With three arms both SHALL be the probability that the leader is the best of all arms, estimated from the arms' means and standard errors with a fixed seed so that the same input gives the same output.

#### Scenario: Disagreement visible
- **WHEN** raw P2BB of arm B is 0.0 and expected P2BB of arm B is 0.9976
- **THEN** the output has `p2bb_raw` 0.0 and `p2bb_expected` 0.9976 for leader B

#### Scenario: Three arms
- **WHEN** a test has three arms and two of them are equal and slightly behind the leader
- **THEN** `p2bb_expected` is the probability that the leader beats both, lower than its probability of beating either one alone, and repeated runs give the same value

### Requirement: Next action
The system SHALL report `next_action` and its `next_action_basis`:
- `confirmed` → `ship_leader`, basis `verdict`;
- `tie` → `ship_either`, basis `verdict`;
- `not_enough_data` → `come_back`, basis `verdict`;
- `keep_running` when the test has reached its horizon (the judging day is on or after start + horizon, so there is nothing left to wait for) → `ship_leader` when `p2bb_expected` ≥ 0.80, otherwise `ship_either`, basis `horizon`;
- `keep_running` otherwise → `ship_leader`, basis `money`, when `p2bb_expected` ≥ 0.80 and `loss_if_ship_leader_now` is below `cost_until_come_back`; otherwise `come_back`, basis `verdict`.
The verdict itself SHALL NOT change because of money: `keep_running` with `ship_leader` means the leader is not proven, but waiting is expected to cost more than shipping it. Below 0.80 the system SHALL never advise shipping the leader, however expensive waiting is.

#### Scenario: Unsure leader is not shipped on money
- **WHEN** the verdict is `keep_running`, `p2bb_expected` is 0.70, `cost_until_come_back` is $3,282 and `loss_if_ship_leader_now` is $3,273
- **THEN** `next_action` is `come_back` and `next_action_basis` is `verdict`

#### Scenario: Horizon reached without a winner
- **WHEN** the verdict is `keep_running`, the test is older than the horizon, and `p2bb_expected` is 0.70
- **THEN** `next_action` is `ship_either` and `next_action_basis` is `horizon`

#### Scenario: Horizon reached with a likely leader
- **WHEN** the verdict is `keep_running`, the test is older than the horizon and `p2bb_expected` is 0.90
- **THEN** `next_action` is `ship_leader` and `next_action_basis` is `horizon`

#### Scenario: Nothing to wait for before the horizon is not the horizon
- **WHEN** the verdict is `keep_running` on day 40 of a 60-day horizon and the come-back date falls on the judging day
- **THEN** `next_action_basis` is not `horizon` and `come_back_on` is after the judging day

#### Scenario: Waiting costs more than the risk
- **WHEN** the verdict is `keep_running`, `cost_until_come_back` is $4,000 and `loss_if_ship_leader_now` is $900
- **THEN** `next_action` is `ship_leader` and `next_action_basis` is `money`

#### Scenario: Risk costs more than waiting
- **WHEN** the verdict is `keep_running`, `cost_until_come_back` is $300 and `loss_if_ship_leader_now` is $2,500
- **THEN** `next_action` is `come_back` and `next_action_basis` is `verdict`

#### Scenario: Confirmed ships the leader
- **WHEN** the verdict is `confirmed`
- **THEN** `next_action` is `ship_leader` and `next_action_basis` is `verdict`

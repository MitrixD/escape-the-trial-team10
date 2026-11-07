# Spec Delta

## Purpose

Tells a growth manager or an AI agent whether the leader of an Adapty A/B test can be trusted now, accounting for revenue that has not arrived yet, and when to come back if not.

## ADDED Requirements

### Requirement: Expected revenue per arm
The system SHALL estimate each arm's revenue per user at the test horizon as received revenue plus expected revenue from pending trials plus expected revenue from future renewals. Expectations SHALL come from a calibration table built from the app's own Adapty analytics (trial→paid conversion and renewal revenue per product), applied to per-arm counts by user state (none, trial, active, ended), product and age. The trial and renewal parts SHALL be reported separately per arm.

#### Scenario: Pending trials count toward expected revenue
- **WHEN** an arm has $0 received and 66 users in an active trial of a product whose calibrated trial→paid conversion and renewal value are positive
- **THEN** the arm's expected revenue is greater than $0 and `revenue_expected_trials` is greater than 0

#### Scenario: Up-front arm has no future revenue
- **WHEN** an arm's paying users all hold a product with no renewals inside the horizon
- **THEN** `revenue_expected_renewals` for that arm is 0 or negative (expected refunds only)

#### Scenario: Counts and per-user data agree
- **WHEN** the estimate is computed from per-arm state counts and from the same users one by one with the same calibration
- **THEN** both give the same expected revenue per user within $0.01

### Requirement: Horizon
The horizon in days SHALL be a parameter of the call. When omitted it SHALL be 60. A horizon below 1 SHALL be rejected with an error. The test goal SHALL NOT be parsed for a horizon.

#### Scenario: Caller horizon
- **WHEN** the caller passes a horizon of 30 days
- **THEN** `horizon_days` is 30 and the expected revenue is computed to day 30

#### Scenario: Default horizon
- **WHEN** no horizon is passed
- **THEN** `horizon_days` is 60

#### Scenario: Horizon below one day
- **WHEN** the caller passes a horizon of 0
- **THEN** the system returns an error and no verdict

### Requirement: Verdict rules
The system SHALL return exactly one verdict, checked in this order: `not_enough_data` (an arm below 30 purchases plus trials, or no calibration); `confirmed` (expected P2BB of the leader ≥ 0.95); `tie` (maturity ≥ 0.80 and the 95% interval of |Δ expected revenue per user| lies below the MDE, 5% of the leader's value); otherwise `keep_running`. Maturity is received divided by expected revenue across arms.

#### Scenario: Too little data
- **WHEN** one arm has 12 purchases and trials combined
- **THEN** the verdict is `not_enough_data` with reason `min_events`

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

### Requirement: Verdict reason
`reason` SHALL name why the test is undecided: `min_events` or `no_calibration` for `not_enough_data`; `pending_revenue` (maturity below 0.80) or `underpowered` for `keep_running`; `null` otherwise.

#### Scenario: Reason for missing calibration
- **WHEN** the verdict is `not_enough_data` because the app has no usable history
- **THEN** `reason` is `no_calibration`

### Requirement: Come-back date for too little data
For `not_enough_data` with reason `min_events`, `come_back_on` SHALL be today plus the days needed to reach 30 events at the observed daily rate; when an arm has no events at all there is no rate and it SHALL be `null`. With reason `no_calibration` it SHALL be `null`.

#### Scenario: Date to reach the minimum
- **WHEN** an arm has 12 events after 3 days
- **THEN** `come_back_on` is today + 5 days

#### Scenario: No events at all
- **WHEN** an arm has 0 purchases and 0 trials
- **THEN** the verdict is `not_enough_data` with reason `min_events` and `come_back_on` is `null`

### Requirement: Come-back date for keep running
For `keep_running`, `come_back_on` SHALL be the later of two dates: test start + the longest trial length among the arms' products + 30 days; and today + the days until the sample reaches the size needed to detect the current difference at 95% with the observed daily traffic. It SHALL be capped at start + horizon and never be before today.

#### Scenario: Date for pending revenue
- **WHEN** a test with 7-day trials started on 7 Nov and the verdict is `keep_running` with reason `pending_revenue`
- **THEN** `come_back_on` is on or after 14 Dec and not after start + horizon

### Requirement: No date when decided
For `confirmed` and `tie`, `come_back_on` SHALL be `null`.

#### Scenario: No date when decided
- **WHEN** the verdict is `confirmed`
- **THEN** `come_back_on` is `null`

### Requirement: Raw P2BB shown next to expected P2BB
The system SHALL report both P2BB on received revenue (`p2bb_raw`) and P2BB on expected revenue (`p2bb_expected`) for the leader, so the reader sees when they disagree.

#### Scenario: Disagreement visible
- **WHEN** raw P2BB of arm B is 0.0 and expected P2BB of arm B is 0.9976
- **THEN** the output has `p2bb_raw` 0.0 and `p2bb_expected` 0.9976 for leader B

### Requirement: Probabilities never round up into confirmed
The system SHALL report `p2bb_expected`, `p2bb_raw` and `maturity` floored to 4 decimals, and the verdict rules SHALL use these floored values, so a verdict that is not `confirmed` never shows 0.95 and the shown maturity is the one the rules saw.

#### Scenario: Just under the threshold
- **WHEN** P2BB on expected revenue is 0.949996
- **THEN** `p2bb_expected` is 0.9499 and the verdict is not `confirmed`

#### Scenario: Maturity just under 0.80
- **WHEN** the received share of expected revenue is 0.799996 and the verdict is `keep_running`
- **THEN** `maturity` is 0.7999 and the reason is `pending_revenue`

### Requirement: At least two arms
The system SHALL reject a test with fewer than two arms with the error "an A/B test needs at least two arms".

#### Scenario: Single arm
- **WHEN** the test has one arm
- **THEN** the system returns that error and no verdict

### Requirement: Output contract
The system SHALL return one JSON object with exactly these fields: `ab_test_id`, `verdict`, `reason`, `leader`, `p2bb_expected`, `p2bb_raw`, `maturity`, `horizon_days`, `come_back_on`, `arms[]`, `calibration_source`, `expected_gap_per_user`. Each arm has `title`, `users`, `revenue_received`, `revenue_expected_trials`, `revenue_expected_renewals` and `revenue_expected_total` (received + trials + renewals), in USD per user, rounded to 2 decimals from unrounded values. `expected_gap_per_user` SHALL be the leader's expected total minus the best other arm's expected total, in USD per user, 2 decimals, never below 0. The JSON SHALL contain no free text written by a model.

#### Scenario: Valid output
- **WHEN** a verdict is produced for any test
- **THEN** the output validates against the JSON schema shipped with the tool

#### Scenario: Reason only when undecided
- **WHEN** the verdict is `confirmed` or `tie`
- **THEN** `reason` is `null` and `calibration_source` is one of `product`, `app`, `none`

#### Scenario: Expected totals and gap
- **WHEN** a verdict is produced for a test with two or more arms
- **THEN** each arm's `revenue_expected_total` equals the estimator's received + trials + renewals per user rounded to 2 decimals, and `expected_gap_per_user` equals the leader's total minus the best other arm's total, rounded to 2 decimals and at least 0

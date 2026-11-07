# Spec Delta

## Purpose

Tells a growth manager or an AI agent whether the leader of an Adapty A/B test can be trusted now, accounting for revenue that has not arrived yet, and what to do next.

## ADDED Requirements

### Requirement: Expected revenue per arm
The system SHALL estimate each arm's revenue per user at the test horizon as received revenue plus expected revenue from pending trials plus expected revenue from future renewals. Expectations SHALL come from a calibration table of mean future revenue by user state (none, trial, active, ended), product and age, built from users outside the test. The horizon SHALL be the number of days in the test goal when present, otherwise 60.

#### Scenario: Pending trials count toward expected revenue
- **WHEN** an arm has $0 received and 66 users in an active trial of a product whose calibrated future value is positive
- **THEN** the arm's expected revenue is greater than $0 and the trial part is reported separately

#### Scenario: Horizon from goal
- **WHEN** the test goal reads "Find which onboarding offer maximises 60-day revenue per install"
- **THEN** the horizon is 60 days

#### Scenario: Counts and per-user data agree
- **WHEN** the estimate is computed from per-arm state counts and from the same users one by one
- **THEN** both give the same expected revenue per user within $0.01

### Requirement: Verdict rules
The system SHALL return exactly one verdict, checked in this order:
1. `not_enough_data` when any arm has fewer than 30 purchases plus trials;
2. `confirmed` when P2BB on expected revenue of the leader is at least 95%;
3. `early` when P2BB is below 95% and maturity (received / expected revenue across arms) is below 80%;
4. `tie` otherwise.

#### Scenario: Too little data
- **WHEN** one arm has 12 purchases and trials combined
- **THEN** the verdict is `not_enough_data` and `come_back_on` is the date when 30 is reached at the current daily traffic

#### Scenario: Confident before maturity
- **WHEN** P2BB on expected revenue is 97% and maturity is 40%
- **THEN** the verdict is `confirmed`, not `early`

#### Scenario: Immature and unsure
- **WHEN** P2BB on expected revenue is 70% and maturity is 50%
- **THEN** the verdict is `early` with a `come_back_on` date when pending trials and the first renewal of the slowest product have matured

#### Scenario: Mature and unsure
- **WHEN** P2BB on expected revenue is 70% and maturity is 90%
- **THEN** the verdict is `tie`

### Requirement: Raw P2BB shown next to expected P2BB
The system SHALL report both P2BB on received revenue and P2BB on expected revenue, so the reader sees when they disagree.

#### Scenario: Disagreement visible
- **WHEN** raw P2BB of arm B is 100% and expected P2BB of arm B is 60%
- **THEN** the output has `p2bb_raw` 1.0 and `p2bb_expected` 0.6 for leader B

### Requirement: Money at stake
The system SHALL report money at stake in USD as the difference in expected revenue per user between arms × daily traffic of the test × a decision lifetime of 180 days, weighted by the probability that the chosen leader is wrong.

#### Scenario: Equal arms
- **WHEN** both arms have the same expected revenue per user
- **THEN** money at stake is 0

### Requirement: Guardrail warnings never change the verdict
The system SHALL compute refunds per paying user and trial cancellations within the same product and trial length for each arm. A metric SHALL get status `worse` when it is at least 1.5× the other arm and the difference is significant at 5%. Warnings SHALL NOT change the verdict; a `worse` warning SHALL add an alternative next test aimed at that metric.

#### Scenario: Refunds per user differ but per payer do not
- **WHEN** arm B has 2.4× the refunds per user of arm A but 1.2× the refunds per payer
- **THEN** the refund warning status is `ok` and the verdict is unchanged

#### Scenario: Real guardrail problem
- **WHEN** arm B's refunds per payer are 2× arm A's and significant
- **THEN** the warning status is `worse`, the verdict is unchanged, and `next_step.alternative` targets refunds

### Requirement: Segments survive correction or are not reported
In offline mode the system SHALL test each value of platform, acquisition channel, onboarding goal and push opt-in for a different effect than the rest of the test, skipping values with fewer than 100 users per arm, and SHALL apply a Bonferroni correction over all comparisons. Only segments with corrected p below 0.05 SHALL appear in `segments_found`; `segments_checked` SHALL report how many were tested.

#### Scenario: Tempting noise rejected
- **WHEN** test Settings shows a $3.07 lift on iOS and none on Android with corrected p of 1.0
- **THEN** `segments_found` is empty and `segments_checked` is greater than 0

#### Scenario: Random segments rejected
- **WHEN** 20 random segments with no real effect are added
- **THEN** at most one appears in `segments_found` across 20 runs

### Requirement: Typed next step
The system SHALL attach a next step whose type follows the verdict: `extend` for `not_enough_data` and `early`, `stop_with_winner` for `confirmed`, `change_lever` for `tie`. The next step SHALL name the placement, the primary metric and the metrics to watch.

#### Scenario: Tie advice
- **WHEN** the verdict is `tie`
- **THEN** `next_step.type` is `change_lever` and the reason says not to repeat the same test

### Requirement: Output contract
The system SHALL return one JSON object with the fields `ab_test_id`, `verdict`, `leader`, `p2bb_expected`, `p2bb_raw`, `horizon_days`, `maturity`, `come_back_on`, `money_at_stake_usd`, `arms[]` (`title`, `users`, `revenue_received`, `revenue_expected_trials`, `revenue_expected_renewals`, `warnings[]`), `segments_checked`, `segments_found[]` and `next_step`. The JSON SHALL contain no free text written by a model.

#### Scenario: Valid output
- **WHEN** a verdict is produced for any test
- **THEN** the output validates against the JSON schema shipped with the tool

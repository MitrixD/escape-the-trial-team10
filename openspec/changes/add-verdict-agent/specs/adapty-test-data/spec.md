# Spec Delta

## Purpose

Collects, read-only and within the hackathon's API rules, the per-arm and per-product counts of one Adapty A/B test and the app history needed to calibrate expected revenue.

## ADDED Requirements

### Requirement: Read-only access
The system SHALL only read from Adapty. It SHALL NOT start, stop, create, update, replace or archive anything.

#### Scenario: No mutating commands
- **WHEN** the data layer runs for any test
- **THEN** every Adapty command it issues is a read command (`get`, `list`, `metrics`, `analytics`)

### Requirement: Per-arm counts
For a given test ID the system SHALL read the test, its arms with their flows, the test goal and placement, and per-arm users, revenue, purchases, trials, finished trials, paid subscribers and refunds.

#### Scenario: Live Onboarding test
- **WHEN** the system reads test "Onboarding: annual trial vs weekly first"
- **THEN** it returns two arms with users 285 and 254 and trials 71 and 66, matching `ab-tests metrics total`

### Requirement: Per-arm counts by product
The system SHALL read each arm's trials and purchases grouped by store product, filtering by the arm's flow and by the test's placement, because one flow can serve several placements.

#### Scenario: Flow used in several places
- **WHEN** an arm's flow also serves another audience or test
- **THEN** only events from the test's placement are counted

### Requirement: Calibration inputs
In live mode the system SHALL build the calibration table from the offline Lumen dataset for the resolved horizon, SHALL exclude the offline test whose name equals the live test title (Lumen's live users are copies of offline users, so including that test leaks their future), and SHALL mark the output `calibration_source` as `offline_calibration`.

#### Scenario: Live test excluded from calibration
- **WHEN** the live test is "Onboarding: annual trial vs weekly first"
- **THEN** the calibration is built without the offline users of that test and `calibration_source` is `offline_calibration`

### Requirement: Gentle on the API
The system SHALL issue Adapty calls one at a time, at no more than 2 per second, SHALL NOT enumerate or read individual profiles, and SHALL stop with a clear error on a 429 instead of retrying in a loop.

#### Scenario: Rate limit hit
- **WHEN** Adapty answers 429 with `retry_after_seconds`
- **THEN** the system reports the wait time and exits without further calls

### Requirement: Account check
Before the first read the system SHALL confirm the CLI is logged in to the team's company and that the test belongs to the Lumen app, and SHALL stop otherwise.

#### Scenario: Wrong account
- **WHEN** the CLI is logged in to another company
- **THEN** the system stops before any data read with a message that names the `ADAPTY_EXPECTED_COMPANY` setting but never its value or any `whoami` value

### Requirement: Secret-returning commands are blocked
The system SHALL refuse to run `apps get`, because its response contains the app secret key, even though it is a read command.

#### Scenario: apps get refused
- **WHEN** any code path asks the CLI wrapper to run `apps get`
- **THEN** the wrapper raises before running the command

### Requirement: Converted trials are counted per product
For each arm and product the system SHALL take trial→paid conversions from the first funnel step after `Trial` (`Paid` if present, otherwise `1 period`), SHALL reconcile their sum with the arm's `trials_paid` from the test metrics, and SHALL place converted users in the `active` group (trial n = trials − converted; active n = direct purchases + converted).

#### Scenario: Funnel without a Paid step
- **WHEN** a product's funnel has `Trial` 45 and `1 period` 15 and the metrics say `trials_paid` 15
- **THEN** the arm has 30 users in `trial` and 15 more in `active` for that product

### Requirement: Live user ages and expired trials
In live mode the system SHALL treat every user of the test as installed on the test's start day, and SHALL move a `trial` group whose age exceeds its product's trial length to `ended` with no further expected trial revenue.

#### Scenario: Weekly trials expired
- **WHEN** the test is 5 days old and a product has a 3-day trial
- **THEN** that product has no `trial` group and its expected trial revenue is 0


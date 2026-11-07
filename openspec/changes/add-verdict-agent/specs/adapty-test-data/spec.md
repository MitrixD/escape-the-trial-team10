# Spec Delta

## Purpose

Collects, read-only and within the hackathon's API rules, everything the verdict needs from Adapty for one A/B test: per-arm and per-product counts of the test, and the app's own history for calibration. Replays recorded responses for tests, eval and demo fallback.

## ADDED Requirements

### Requirement: Read-only access
The system SHALL only read from Adapty. It SHALL NOT start, stop, create, update, replace or archive anything.

#### Scenario: No mutating commands
- **WHEN** the data layer runs for any test
- **THEN** every Adapty command it issues is a read command (`get`, `list`, `metrics`, `analytics`, `auth whoami`)

### Requirement: Secret-returning commands are blocked
The system SHALL refuse to run `apps get`, because its response contains the app secret key, even though it is a read command.

#### Scenario: apps get refused
- **WHEN** any code path asks the CLI wrapper to run `apps get`
- **THEN** the wrapper raises before running the command

### Requirement: Per-arm counts
For a given test ID the system SHALL read the test, its arms with their flows, the test goal, placement and start date, and per-arm users, revenue, purchases, trials and paid trials.

#### Scenario: Live Onboarding test
- **WHEN** the system reads test "Onboarding: annual trial vs weekly first"
- **THEN** it returns two arms with users 285 and 254 and trials 71 and 66, matching `ab-tests metrics total`

### Requirement: Per-arm counts by product
The system SHALL read each arm's trials and purchases grouped by store product, filtering by the arm's flow and by the test's placement, because one flow can serve several placements, and SHALL map the App Store and Play keys of the same product to one product key using the app's own product catalog read from Adapty (`products list`: each product with its store product IDs). No mapping specific to one app SHALL live in code.

#### Scenario: Product keys from the catalog
- **WHEN** the funnel reports a product once under its App Store title and once under its Play key, and both IDs belong to one product in the catalog
- **THEN** their counts are merged under that one product

#### Scenario: Funnel lags the test metrics
- **WHEN** the funnel's per-product trials or purchases do not add up to the arm's metrics
- **THEN** the per-product counts are scaled to the metrics `trials` and `unique_paid_subscribers`, the arm's groups add up to the metrics revenue, and a warning is written to stderr

#### Scenario: Flow used in several places
- **WHEN** an arm's flow also serves another audience or test
- **THEN** only events from the test's placement are counted

### Requirement: Converted trials are counted per product
For each arm and product the system SHALL take trial→paid conversions from the first funnel step after `Trial` (`Paid` if present, otherwise `1 period`), SHALL reconcile their sum with the arm's paid trials from the test metrics, and SHALL place converted users in the `active` group (trial n = trials − converted; active n = direct purchases + converted).

#### Scenario: Funnel without a Paid step
- **WHEN** a product's funnel has `Trial` 45 and `1 period` 15 and the metrics say 15 paid trials
- **THEN** the arm has 30 users in `trial` and 15 more in `active` for that product

### Requirement: Live user ages and expired trials
The system SHALL treat every user of the test as installed on the test's start day, and SHALL move a `trial` group whose age exceeds its product's trial length to `ended` with no further expected trial revenue.

#### Scenario: Weekly trials expired
- **WHEN** the test is 5 days old and a product has a 3-day trial
- **THEN** that product has no `trial` group and its expected trial revenue is 0

### Requirement: Calibration from the app's own history
The system SHALL build the calibration table from analytics of the same app, read through any Adapty API (Developer CLI, Export Analytics API or Server-side API): trial→paid conversion per product (`conversion`, `trial-paid`, by store product), cumulative revenue per paying subscriber by day since subscription start per product (`ltv` by store product, revenue basis as Adapty returns it) and each product's trial length, taken from the first day its `ltv` curve turns positive. The system SHALL NOT read any dataset outside Adapty at run time.

#### Scenario: Calibration from recorded analytics of the test app
- **WHEN** the recorded `conversion` and `ltv` responses of the test app are given for horizon 60
- **THEN** the table has a renewal value curve for every product in `ltv`, a trial→paid rate for every product with trials in `conversion`, and `calibration_source` is `product`

#### Scenario: History window ends before the test start
- **WHEN** the analytics commands accept a date range
- **THEN** the calibration reads are issued with `--date-from` 180 days before the test start and `--date-to` the day before the test start

#### Scenario: Trial length from the LTV curve
- **WHEN** a product with trials in `conversion` has an `ltv` curve that is 0 until day 3 and positive from day 3
- **THEN** its trial length is 3 days, and a product without trials has trial length 0

#### Scenario: Product keys normalised
- **WHEN** the same product appears under a store key and a product UUID in the analytics responses
- **THEN** both rows are merged under one product key

### Requirement: Calibration fallback inside Adapty data
When a product has no history, the system SHALL use the app-wide trial→paid rate and renewal value and SHALL report `calibration_source` as `app`. When the app has no usable history at all, the verdict SHALL be `not_enough_data` with reason `no_calibration` and `calibration_source` `none`.

#### Scenario: New product
- **WHEN** an arm sells a product with no rows in the app's conversion and ltv history
- **THEN** its groups use the app-wide rates and the output says `calibration_source: app`

#### Scenario: Empty app history
- **WHEN** the ltv response contains no rows
- **THEN** the verdict is `not_enough_data` with reason `no_calibration`

### Requirement: Gentle on the API
The system SHALL issue Adapty calls one at a time, at no more than 2 per second, SHALL NOT enumerate or read individual profiles, and SHALL stop with a clear error on a 429 instead of retrying in a loop. One verdict SHALL need no more than 10 Adapty calls, including the product catalog read.

#### Scenario: Rate limit hit
- **WHEN** Adapty answers 429 with `retry_after_seconds`
- **THEN** the system reports the wait time and exits without further calls

### Requirement: Account check
Before the first read the system SHALL confirm the CLI is logged in to the team's company and that the test belongs to the configured app, and SHALL stop otherwise.

#### Scenario: Wrong account
- **WHEN** the CLI is logged in to another company
- **THEN** the system stops before any data read with a message that names the `ADAPTY_EXPECTED_COMPANY` setting but never its value or any `whoami` value

### Requirement: Replay of recorded responses
The system SHALL accept a replay directory of recorded Adapty responses, keyed by command, and SHALL run the same code path on them without any network call.

#### Scenario: Replay of the live Onboarding run
- **WHEN** the tool runs with `--replay` on the recorded Onboarding responses
- **THEN** it produces the same JSON as the live run, and no subprocess or HTTP call is made

#### Scenario: Missing recording
- **WHEN** a command needed for the verdict has no file in the replay directory
- **THEN** the system returns an error naming the command and makes no network call

### Requirement: Any Adapty app
The system SHALL take the app ID from `ADAPTY_APP_ID` in `.env` or from the call, and SHALL read the same commands for any app. No threshold, product name, flow or placement of a particular app SHALL be hard-coded; the test app (Lumen) appears only in recorded fixtures and the eval.

#### Scenario: Another app
- **WHEN** `ADAPTY_APP_ID` points to a different app with its own products and history
- **THEN** the system reads that app's test, catalog and analytics with the same commands and builds its calibration from that app's history


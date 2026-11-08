# adapty-test-data Specification

## Purpose
Collects, read-only and within the hackathon's API rules, everything the verdict needs from Adapty for one A/B test: per-arm and per-product counts of the test, and the app's own history for calibration. Replays recorded responses for tests, eval and demo fallback.

## Requirements

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
For a given test ID the system SHALL read the test, its arms with their flows, the test goal, placement and start date, and per-arm users, revenue, purchases, trials and paid trials. Each arm's metrics row SHALL be matched by its variation ID or its flow or paywall ID, never by position; an arm without a matching row SHALL be an error naming the arm.

#### Scenario: Live Onboarding test
- **WHEN** the system reads test "Onboarding: annual trial vs weekly first"
- **THEN** it returns two arms with users 285 and 254 and trials 71 and 66, matching `ab-tests metrics total`

#### Scenario: Metrics row without a matching ID
- **WHEN** `ab-tests metrics total` has no row whose variation ID or flow ID matches arm A
- **THEN** the system stops with the error "metrics have no row for arm A" instead of taking a row by position

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
The system SHALL assume users arrive uniformly since the test start, without extra Adapty calls. With `D` the days since the start (at least 1), the system SHALL spread a product's active users over ages `d + 0.5` for `d = 0 … D−1`; of a product's unconverted trials with trial length `t`, the share `min(1, t / D)` SHALL stay `trial`, spread over ages `d + 0.5` for `d = 0 … min(D, t)−1`, and the rest SHALL be `ended`. Counts per age SHALL be integers by largest remainder and SHALL still reproduce the test metrics. The system SHALL move a `trial` group whose age exceeds its product's trial length to `ended` with no further expected trial revenue.

#### Scenario: Test 10 days old with a 3-day trial
- **WHEN** the test is 10 days old and a product with a 3-day trial has 100 unconverted trials
- **THEN** 30 of them are `trial` with ages 0.5, 1.5 and 2.5 (10 each), and the other 70 are `ended`

#### Scenario: Active users spread over the test period
- **WHEN** the test is 4 days old and a product has 8 active users
- **THEN** that product has 2 active users at each of the ages 0.5, 1.5, 2.5 and 3.5, each with the same received revenue

#### Scenario: Old trial groups expire
- **WHEN** a `trial` group is older than its product's 3-day trial
- **THEN** it becomes `ended` and its expected trial revenue is 0

### Requirement: Calibration from the app's own history
The system SHALL build the calibration table from analytics of the same app, read through the Developer CLI: trial→paid conversion per product (`conversion`, `trial-paid`, by store product), cumulative revenue per paying subscriber by day since subscription start per product (`ltv` by store product, revenue basis as Adapty returns it) and each product's trial length, taken from the first day its `ltv` curve turns positive. The system SHALL NOT read any dataset outside Adapty at run time.

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
- **THEN** that product's groups are valued with the app-wide rate and curve, and `calibration_source` reports the whole calibration: `product` when any product of the app has its own curve, `app` when only the app-wide curve exists

#### Scenario: Empty app history
- **WHEN** the ltv response contains no rows and every arm has at least 30 events
- **THEN** the verdict is `not_enough_data` with reason `no_calibration` (an arm below 30 events gives `min_events` first)

### Requirement: Gentle on the API
The system SHALL issue Adapty calls one at a time, at no more than 2 per second, SHALL NOT enumerate or read individual profiles, and SHALL stop with a clear error on a 429 instead of retrying in a loop. One verdict SHALL need no more than 10 Adapty calls, including the product catalog read: `auth whoami`, `products list`, `ab-tests get`, `ab-tests metrics total`, one `analytics funnel` per arm, `analytics conversion` and `analytics ltv` (8 for two arms). `analytics cohort` SHALL NOT be read: it has no product grouping. Tests with more than 3 arms SHALL be rejected with a clear error before any funnel read.

#### Scenario: Rate limit hit
- **WHEN** Adapty answers 429 with `retry_after_seconds`
- **THEN** the system reports the wait time and exits without further calls

#### Scenario: Rate limit without a usable wait time
- **WHEN** Adapty answers 429 with a `retry_after_seconds` that is not a number
- **THEN** the system reports that the retry time is unknown and exits without further calls

### Requirement: Account check
Before the first read the system SHALL confirm the CLI is logged in to the team's company, and SHALL stop otherwise. The test's ownership check is `ab-tests get` scoped with `--app`: a test of another app is not found, and the system stops with an error naming the test ID. On replay the recorded `matched_expected_company` flag of `auth_whoami.json` is the account check.

#### Scenario: Wrong account
- **WHEN** the CLI is logged in to another company
- **THEN** the system stops before any data read with a message that names the `ADAPTY_EXPECTED_COMPANY` setting but never its value or any `whoami` value

#### Scenario: Test of another app
- **WHEN** `ab-tests get <id> --app <app>` fails because the test is not in the configured app
- **THEN** the error is "cannot read A/B test <id>: adapty exited with code <n>" and contains no app ID

### Requirement: Replay of recorded responses
The system SHALL accept a replay directory of recorded Adapty responses, keyed by command, and SHALL run the same code path on them without any network call. A bundle SHALL carry `as_of.json` (`{"as_of": "YYYY-MM-DD"}`, the recording day); on replay the test is judged as of that day unless the call passes an as-of date, and a bundle without it is an error that asks for `--as-of`. Replay SHALL NOT read `.env` or the environment: it uses a placeholder app ID and company, so errors cannot contain configured values.

#### Scenario: Replay of a recorded bundle
- **WHEN** the tool runs twice with `--replay` on the same recorded bundle, on different days
- **THEN** both runs give byte-identical JSON, equal to the live run when the bundle and the run were taken on the same day (`as_of`), and no subprocess or HTTP call is made

#### Scenario: Bundle without a recording day
- **WHEN** the replay directory has no `as_of.json` and no as-of date is passed
- **THEN** the system returns an error naming `as_of.json` and `--as-of`

#### Scenario: Replay ignores configuration
- **WHEN** `ADAPTY_APP_ID` is set in the environment or `.env` and a replay run fails
- **THEN** the error and stderr do not contain that value

#### Scenario: Missing recording
- **WHEN** a command needed for the verdict has no file in the replay directory
- **THEN** the system returns an error naming the command and makes no network call

### Requirement: Any Adapty app
The system SHALL take the app ID from the call (CLI `--app`, MCP `app_id`) or from `ADAPTY_APP_ID`, and SHALL read the same commands for any app. The call wins over configuration; an environment variable wins over the same key in the `.env` file. The `.env` file is read from the working directory, or from the repository root when the working directory has none. No threshold, product name, flow or placement of a particular app SHALL be hard-coded; the test app (Lumen) appears only in recorded fixtures and the eval.

#### Scenario: Another app
- **WHEN** `ADAPTY_APP_ID` points to a different app with its own products and history
- **THEN** the system reads that app's test, catalog and analytics with the same commands and builds its calibration from that app's history

#### Scenario: App ID from the call
- **WHEN** the call passes an app ID and `ADAPTY_APP_ID` names another app
- **THEN** every data read uses the app ID from the call, and no error contains it

# Spec Delta

## ADDED Requirements

### Requirement: Test state
The system SHALL read the test's state and dates from `ab-tests get`. A test that has not started (no `started_at`, for example a draft) SHALL be rejected with an error naming the test. For a test that has stopped, the running period SHALL end on its `stopped_at` day: daily traffic is counted over the running period, and user ages are measured from the judging day, so users who arrived during the running period are at least as old as the time since the stop.

#### Scenario: Draft test
- **WHEN** `ab-tests get` returns a test with `started_at` null
- **THEN** the system returns an error naming the test as not started, and no verdict

#### Scenario: Stopped test judged later
- **WHEN** a test ran 3 days, stopped, and is judged 30 days after its start
- **THEN** traffic per day is the test's users divided by 3, not by 30, and no user is younger than 27 days

## MODIFIED Requirements

### Requirement: Live user ages and expired trials
The system SHALL assume users arrive uniformly over the test's running period, without extra Adapty calls. With `D` the days of the running period (at least 1) and `O` the days since the running period ended (0 for a live test), arrival day `d` gives age `O + d + 0.5` for `d = 0 … D−1`. A product's active users SHALL be spread over these ages, except that users who converted from a trial of length `t` SHALL be at least `t` days old, because they paid after their trial. Of a product's trial starts, the share `min(1, t / D)` of all starts, but no more than the unconverted ones, SHALL stay `trial`, spread over the youngest ages below `t`; the rest of the unconverted SHALL be `ended`. Counts per age SHALL be integers by largest remainder and SHALL still reproduce the test metrics. The system SHALL move a `trial` group whose age exceeds its product's trial length to `ended` with no further expected trial revenue.

#### Scenario: Test 10 days old with a 3-day trial
- **WHEN** a live test is 10 days old and a product with a 3-day trial has 100 trial starts, none converted
- **THEN** 30 of them are `trial` with ages 0.5, 1.5 and 2.5 (10 each), and the other 70 are `ended`

#### Scenario: Pending share counts all trial starts
- **WHEN** a live test is 10 days old and a product with a 3-day trial has 100 trial starts of which 50 converted
- **THEN** 30 of the 50 unconverted are `trial` and 20 are `ended`

#### Scenario: Converted trial users are at least as old as the trial
- **WHEN** a live test is 10 days old and a product with a 7-day trial has converted users
- **THEN** none of those active users is younger than 7 days

#### Scenario: Active users spread over the test period
- **WHEN** a live test is 4 days old and a product without a trial has 8 active users
- **THEN** that product has 2 active users at each of the ages 0.5, 1.5, 2.5 and 3.5, each with the same received revenue

#### Scenario: Old trial groups expire
- **WHEN** a `trial` group is older than its product's 3-day trial
- **THEN** it becomes `ended` and its expected trial revenue is 0

### Requirement: Calibration from the app's own history
The system SHALL build the calibration table from analytics of the same app, read through the Developer CLI: trial→paid conversion per product (`conversion`, `trial-paid`, by store product), cumulative revenue per paying subscriber by day per product (`ltv` by store product, revenue basis as Adapty returns it), each product's trial length, taken from the first day its `ltv` curve turns positive, and each product's period from the product catalog. A product whose trial length comes out as 0 while the test's funnel shows trials for it SHALL use 7 days, and the system SHALL log a warning. The system SHALL NOT read any dataset outside Adapty at run time.

#### Scenario: Calibration from recorded analytics of the test app
- **WHEN** the recorded `conversion` and `ltv` responses of the test app are given for horizon 60
- **THEN** the table has a renewal value curve for every product in `ltv`, a trial→paid rate for every product with trials in `conversion`, and `calibration_source` is `product`

#### Scenario: History window ends before the test start
- **WHEN** the analytics commands accept a date range
- **THEN** the calibration reads are issued with `--date-from` 180 days before the test start and `--date-to` the day before the test start

#### Scenario: Trial length from the LTV curve
- **WHEN** a product with trials in `conversion` has an `ltv` curve that is 0 until day 3 and positive from day 3
- **THEN** its trial length is 3 days, and a product without trials has trial length 0

#### Scenario: Unknown trial length for a product with trials in the test
- **WHEN** a product has trial length 0 from the calibration and the test's funnel shows 20 trials for it
- **THEN** those trials use a 7-day trial length and a warning names the product

#### Scenario: Product keys normalised
- **WHEN** the same product appears under a store key and a product UUID in the analytics responses
- **THEN** both rows are merged under one product key

### Requirement: Replay of recorded responses
The system SHALL accept a replay directory of recorded Adapty responses, keyed by command, and SHALL run the same code path on them without any network call. Funnel recordings SHALL be found for flow tests (`flow_id` filter) and paywall tests (`paywall_id` filter). A bundle SHALL carry `as_of.json` (`{"as_of": "YYYY-MM-DD"}`, the recording day); on replay the test is judged as of that day; a bundle without it is an error that asks for `--as-of`, and then the passed date is taken as the recording day. Recorded bundles SHALL use the same history window as live reads (180 days before the test start). Replay SHALL NOT read `.env` or the environment: it uses a placeholder app ID and company, so errors cannot contain configured values.

#### Scenario: Replay of a recorded bundle
- **WHEN** the tool runs twice with `--replay` on the same recorded bundle, on different days
- **THEN** both runs give byte-identical JSON, equal to the live run when the bundle and the run were taken on the same day (`as_of`), and no subprocess or HTTP call is made

#### Scenario: Replay of a paywall test
- **WHEN** a bundle records a paywall test with funnel files named by paywall ID
- **THEN** the replay produces a verdict without a missing-recording error

#### Scenario: Bundle without a recording day
- **WHEN** the replay directory has no `as_of.json` and no as-of date is passed
- **THEN** the system returns an error naming `as_of.json` and `--as-of`

#### Scenario: Replay ignores configuration
- **WHEN** `ADAPTY_APP_ID` is set in the environment or `.env` and a replay run fails
- **THEN** the error and stderr do not contain that value

#### Scenario: Missing recording
- **WHEN** a command needed for the verdict has no file in the replay directory
- **THEN** the system returns an error naming the command and makes no network call

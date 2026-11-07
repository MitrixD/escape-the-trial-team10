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
The system SHALL read, per store product, the app's historical trial-to-paid conversion and renewal behaviour needed for the calibration table. If a live read is unavailable, the system SHALL fall back to a calibration table built from the offline dataset and SHALL mark the output source as `offline_calibration`.

#### Scenario: Live calibration unavailable
- **WHEN** the conversion read by product fails
- **THEN** the verdict is still produced and its metadata says the calibration came from the offline dataset

### Requirement: Gentle on the API
The system SHALL issue Adapty calls one at a time, at no more than 2 per second, SHALL NOT enumerate or read individual profiles, and SHALL stop with a clear error on a 429 instead of retrying in a loop.

#### Scenario: Rate limit hit
- **WHEN** Adapty answers 429 with `retry_after_seconds`
- **THEN** the system reports the wait time and exits without further calls

### Requirement: Account check
Before the first read the system SHALL confirm the CLI is logged in to the team's company and that the test belongs to the Lumen app, and SHALL stop otherwise.

#### Scenario: Wrong account
- **WHEN** the CLI is logged in to another company
- **THEN** the system stops before any data read and names the expected company

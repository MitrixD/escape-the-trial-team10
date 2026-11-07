# Spec Delta

## Purpose

Exposes the verdict to people and AI agents through a CLI command and an MCP tool with identical output, plus an offline mode for demos and evals.

## ADDED Requirements

### Requirement: CLI command
The system SHALL provide a command that takes an A/B test ID and an optional `--horizon` in days, and prints the verdict JSON to stdout, with a non-zero exit code and a JSON error on failure.

#### Scenario: Live test
- **WHEN** a user runs the command with the ID of a live Lumen test
- **THEN** it prints a verdict JSON and exits 0

#### Scenario: Unknown test
- **WHEN** the ID does not exist in the app
- **THEN** it prints a JSON error naming the ID and exits non-zero

### Requirement: MCP tool
The system SHALL provide a stdio MCP server with one tool that takes a test ID, an optional horizon in days and optional offline parameters, and returns the same JSON as the CLI. The tool description SHALL tell calling agents to run it before stopping a test and to explain the verdict using only numbers from the JSON.

#### Scenario: Same answer on both paths
- **WHEN** the CLI and the MCP tool run on the same test with the same inputs
- **THEN** their JSON outputs are identical

### Requirement: Offline mode
The system SHALL accept an offline test name, an as-of day and a daily traffic, build per-arm counts from the offline Lumen dataset as they would have looked on that day, and run the same verdict code. The output SHALL mark its source as `offline`.

#### Scenario: Settings on day 14
- **WHEN** the tool runs offline on "Settings: upgrade vs lifetime anchor" as of day 14
- **THEN** it returns a verdict whose `source` is `offline` and whose segments section is filled

### Requirement: No model text inside the tool
The tool SHALL NOT call a language model. Explanations SHALL be written by the calling agent from the JSON.

#### Scenario: No LLM dependency
- **WHEN** the tool runs with no LLM API key configured
- **THEN** it returns the full verdict JSON

### Requirement: Adjustable horizon on every entry point
The CLI command, the MCP tool and offline mode SHALL accept an optional horizon in days and pass it to the verdict, which then reports `horizon_source` `parameter`. Calibration SHALL be built for the same horizon.

#### Scenario: Horizon from the CLI
- **WHEN** a user runs the command offline on Settings with `--horizon 90`
- **THEN** the output has `horizon_days` 90 and `horizon_source` `parameter`

### Requirement: Offline inputs are validated
Offline mode SHALL reject `day` or `traffic` below 1 and a `day` greater than the resolved horizon, each with a clear error.

#### Scenario: Day beyond horizon
- **WHEN** offline mode runs with day 31 and horizon 30
- **THEN** it returns "day must not exceed the horizon (30 days)"

### Requirement: Safe errors
Errors from the CLI and the MCP tool SHALL be JSON `{"error": ...}` with no traceback. They SHALL NOT contain values from `.env`, `whoami` output or raw Adapty stderr; unexpected exceptions SHALL show only `unexpected <TypeName>`, with details written to stderr as one line.

#### Scenario: Unexpected failure
- **WHEN** an unexpected FileNotFoundError is raised for the dataset path
- **THEN** the JSON error is `unexpected FileNotFoundError` and the path appears only on stderr

### Requirement: Units in the tool description
The MCP tool description SHALL state that revenue fields in `arms` are USD per user, that `money_at_stake_usd` is a total, and that the renewals part includes expected refunds and can be negative.

#### Scenario: Description states units
- **WHEN** an agent lists the tool
- **THEN** its description contains "USD per user" and "can be negative"


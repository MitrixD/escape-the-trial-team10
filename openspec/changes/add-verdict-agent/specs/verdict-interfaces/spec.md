# Spec Delta

## Purpose

Exposes the verdict to people and AI agents through a CLI command and an MCP tool with identical output.

## ADDED Requirements

### Requirement: CLI command
The system SHALL provide a command that takes an A/B test ID, an optional `--horizon` in days, an optional `--after-days` (days the shipped arm serves traffic after the stop, for money at stake), an optional `--replay <dir>`, an optional `--app <app id>` and an optional `--as-of YYYY-MM-DD`, and prints the verdict JSON to stdout with exit code 0, or a JSON error with a non-zero exit code.

#### Scenario: Live test
- **WHEN** a user runs the command with the ID of a live test of the configured app
- **THEN** it prints a verdict JSON and exits 0

#### Scenario: Unknown test
- **WHEN** the ID does not exist in the app
- **THEN** it prints a JSON error naming the ID and exits non-zero

#### Scenario: Replay
- **WHEN** a user runs the command with `--replay` on a recorded bundle
- **THEN** it prints a verdict JSON and exits 0 without network access, and the same JSON on any day

#### Scenario: As-of date
- **WHEN** a user passes `--as-of 2026-11-20` with `--replay`
- **THEN** the test is judged as of 20 Nov 2026 instead of the bundle's recording day

### Requirement: MCP tool
The system SHALL provide a stdio MCP server with one tool `ab_test_verdict` that takes a test ID, an optional horizon in days, an optional `after_days`, an optional replay directory and an optional app ID, and returns the same JSON as the CLI. The tool description SHALL tell calling agents to run it before stopping a test or choosing a winner, to explain the verdict using only numbers from the JSON, and to pass `horizon` as the number of days the test goal names (for example "60-day revenue" → 60) or omit it when the goal names none. The server SHALL work when started outside the repository: it reads `.env` from the repository root when its working directory has none.

#### Scenario: Same answer on both paths
- **WHEN** the CLI and the MCP tool run on the same test with the same inputs
- **THEN** their JSON outputs are identical

#### Scenario: Horizon from the goal
- **WHEN** an agent lists the tool
- **THEN** its description tells it to pass the number of days named in the test goal as `horizon`, and to omit `horizon` otherwise

#### Scenario: Started from another directory
- **WHEN** the MCP server runs with a working directory that has no `.env`
- **THEN** it reads the `.env` in the repository root

### Requirement: Units in the tool description
The MCP tool description SHALL state that revenue fields in `arms` and `expected_gap_per_user` are USD per user and that the renewals part includes expected refunds and can be negative. It SHALL state that USD values in `money` are totals for the test's traffic, and that `next_action` with basis `money` means the leader is not proven but waiting is expected to cost more than shipping it.

#### Scenario: Description states units
- **WHEN** an agent lists the tool
- **THEN** its description contains "USD per user", "can be negative" and "totals for the test's traffic"

### Requirement: Safe errors
Errors from the CLI and the MCP tool SHALL be JSON `{"error": ...}` with no traceback. They SHALL NOT contain values from `.env`, `whoami` output or raw Adapty stderr. The tool's own validation messages (horizon, arms, missing metrics row, more than 3 arms, missing `as_of.json`, app ID not set) SHALL be shown as written; every other exception, including other `ValueError`s and their subclasses such as `JSONDecodeError`, SHALL show only `unexpected <TypeName>`, with details written to stderr as one line.

#### Scenario: Unexpected failure
- **WHEN** an unexpected FileNotFoundError is raised for the replay path
- **THEN** the JSON error is `unexpected FileNotFoundError` and the path appears only on stderr

#### Scenario: ValueError subclass from a library
- **WHEN** a `JSONDecodeError` reaches the CLI or the MCP tool
- **THEN** the JSON error is `unexpected JSONDecodeError` and its message appears only on stderr

### Requirement: No model text inside the tool
The tool SHALL NOT call a language model. Explanations SHALL be written by the calling agent from the JSON.

#### Scenario: No LLM dependency
- **WHEN** the tool runs with no LLM API key configured
- **THEN** it returns the full verdict JSON

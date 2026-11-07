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

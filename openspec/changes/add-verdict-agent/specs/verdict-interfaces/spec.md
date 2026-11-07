# Spec Delta

## Purpose

Exposes the verdict to people and AI agents through a CLI command and an MCP tool with identical output.

## ADDED Requirements

### Requirement: CLI command
The system SHALL provide a command that takes an A/B test ID, an optional `--horizon` in days and an optional `--replay <dir>`, and prints the verdict JSON to stdout with exit code 0, or a JSON error with a non-zero exit code.

#### Scenario: Live test
- **WHEN** a user runs the command with the ID of a live Lumen test
- **THEN** it prints a verdict JSON and exits 0

#### Scenario: Unknown test
- **WHEN** the ID does not exist in the app
- **THEN** it prints a JSON error naming the ID and exits non-zero

#### Scenario: Replay
- **WHEN** a user runs the command with `--replay` on a recorded bundle
- **THEN** it prints a verdict JSON and exits 0 without network access

### Requirement: MCP tool
The system SHALL provide a stdio MCP server with one tool `ab_test_verdict` that takes a test ID, an optional horizon in days and an optional replay directory, and returns the same JSON as the CLI. The tool description SHALL tell calling agents to run it before stopping a test or choosing a winner and to explain the verdict using only numbers from the JSON.

#### Scenario: Same answer on both paths
- **WHEN** the CLI and the MCP tool run on the same test with the same inputs
- **THEN** their JSON outputs are identical

### Requirement: Units in the tool description
The MCP tool description SHALL state that revenue fields in `arms` are USD per user and that the renewals part includes expected refunds and can be negative.

#### Scenario: Description states units
- **WHEN** an agent lists the tool
- **THEN** its description contains "USD per user" and "can be negative"

### Requirement: Safe errors
Errors from the CLI and the MCP tool SHALL be JSON `{"error": ...}` with no traceback. They SHALL NOT contain values from `.env`, `whoami` output or raw Adapty stderr; unexpected exceptions SHALL show only `unexpected <TypeName>`, with details written to stderr as one line.

#### Scenario: Unexpected failure
- **WHEN** an unexpected FileNotFoundError is raised for the replay path
- **THEN** the JSON error is `unexpected FileNotFoundError` and the path appears only on stderr

### Requirement: No model text inside the tool
The tool SHALL NOT call a language model. Explanations SHALL be written by the calling agent from the JSON.

#### Scenario: No LLM dependency
- **WHEN** the tool runs with no LLM API key configured
- **THEN** it returns the full verdict JSON

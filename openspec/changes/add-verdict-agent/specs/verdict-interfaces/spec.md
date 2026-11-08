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

### Requirement: Stop guard
The system SHALL provide a Claude Code `PreToolUse` hook that runs before an agent stops an Adapty A/B test, through the Adapty MCP tool `ab_tests_stop` or the CLI command `adapty ab-tests stop`, and decides from the verdict of that test. The hook SHALL never stop, start or change a test itself; it only lets the call through to the human (`ask`) or blocks it (`deny`), and its reason SHALL quote only values from the verdict JSON and the test's arms:
- the verdict cannot be produced (error) → `deny`: no stop without a verdict;
- `next_action` is `come_back` → `deny`, naming the verdict, `come_back_on`, `cost_per_day`, `loss_if_ship_leader_now` and `chance_leader_is_wrong` when present;
- `next_action` is `ship_leader` and the chosen winner is another arm → `deny`, naming the verdict leader, its `p2bb_expected` and the chosen arm;
- `next_action` is `ship_leader` and the winner is the leader, or `ship_either` with any winner of the test, or the stop names no winner of the test → `ask`, with the verdict summary, so a human confirms the irreversible stop.
These decisions are the `strict` mode. The guard SHALL also have an `ask` mode, in which every stop is answered `ask`: when `strict` would deny, the reason starts with a warning that the stop goes against the verdict (or that there is no verdict) and carries the same facts. The mode SHALL come from the environment variable `VERDICT_GUARD_MODE` when it is set, otherwise from the `--mode` argument of the hook command, otherwise `ask`; an unknown value SHALL mean `strict`. In `strict`, a deny reason SHALL tell the agent that the user can restart the session with `VERDICT_GUARD_MODE=ask` to confirm the stop themselves. The guard is optional: a project gets it only through `scripts/install_guard.sh <dir> [--mode ask|strict]` (default `ask`) or by adding the hook to its settings by hand.
Commands other than an A/B test stop SHALL pass through with no output. The hook SHALL read the test from a recorded bundle instead of Adapty when the environment variable `VERDICT_GUARD_REPLAY` lists a bundle (paths separated by the OS path separator) whose `ab-tests_get.json` has the stopped test's ID.

#### Scenario: Agent picks the raw-P2BB favourite
- **WHEN** an agent calls `ab_tests_stop` on the synthetic test at day 14 with `winner_flow_id` `annual_upfront`, while the verdict leader is `weekly_trial`
- **THEN** the hook denies the call and the reason names `weekly_trial`, its `p2bb_expected` and `annual_upfront`

#### Scenario: Too early to stop
- **WHEN** the verdict's `next_action` is `come_back`
- **THEN** the hook denies the call and the reason names `come_back_on`

#### Scenario: Winner agrees with the verdict
- **WHEN** the verdict's `next_action` is `ship_leader` and the winner is the leader
- **THEN** the hook answers `ask` and the reason states the leader and `p2bb_expected`

#### Scenario: No verdict, no stop
- **WHEN** the verdict returns an error
- **THEN** the hook denies the call and the reason includes the error

#### Scenario: CLI stop is guarded too
- **WHEN** an agent runs `adapty ab-tests stop <id> --app <app> --winner <flow id>` through Bash
- **THEN** the hook decides exactly as for the MCP tool with the same test, app and winner

#### Scenario: Ask mode hands a disagreeing stop to the human
- **WHEN** the mode is `ask` and an agent stops the synthetic test at day 14 with winner `annual_upfront`
- **THEN** the hook answers `ask`, and the reason starts with a warning and names `weekly_trial` and `annual_upfront`

#### Scenario: The human sets the mode, not the command
- **WHEN** the hook command says `--mode strict` and `VERDICT_GUARD_MODE` is `ask`
- **THEN** the guard runs in `ask` mode

#### Scenario: Unknown mode is strict
- **WHEN** `VERDICT_GUARD_MODE` is `off`
- **THEN** the guard runs in `strict` mode

#### Scenario: Other commands pass
- **WHEN** an agent runs any other Bash command or `adapty ab-tests get`
- **THEN** the hook prints nothing and exits 0

### Requirement: Decision card
The CLI SHALL accept `--format json` (default) or `--format card`. The card is a short text rendering of the same verdict for a person reading a terminal, in the style of experiment platforms' status lines. It SHALL use only values that appear in the verdict JSON, and SHALL contain:
- a status line: `SHIP <leader>` for `next_action` `ship_leader`, `SHIP EITHER` for `ship_either`, `WAIT until <come_back_on>` for `come_back` with a date, `WAIT` without one; followed by the verdict, the reason when present and the `next_action_basis`;
- `p2bb_expected` next to `p2bb_raw`, and `maturity` as a fraction and a percentage of expected revenue received;
- for the leader, revenue per user: received, expected from trials, expected from renewals, expected total;
- when `money` is not `null`: `cost_per_day`, `loss_if_ship_leader_now`, `cost_until_come_back` when present, and `chance_leader_is_wrong`.
On an error the card SHALL be `ERROR: <message>` and the exit code non-zero. The stop guard's reason SHALL start with the same card joined into one line.

#### Scenario: Card for the synthetic trap
- **WHEN** a user runs the CLI with `--format card` on the synthetic test at day 14
- **THEN** the card starts with `SHIP weekly_trial` and contains `0.9994`, `raw 0.0`, `$148.98` and `$2.35`

#### Scenario: Card for a test that is too early
- **WHEN** the verdict is `not_enough_data` with `come_back_on` 2027-01-05
- **THEN** the card starts with `WAIT until 2027-01-05` and has no money line

#### Scenario: Every number in the card comes from the JSON
- **WHEN** the card is rendered for any verdict
- **THEN** `eval/check_agent_text.py` finds every number of the card in the verdict JSON

#### Scenario: Card error
- **WHEN** the verdict cannot be produced
- **THEN** the card is `ERROR: <message>` and the CLI exits non-zero

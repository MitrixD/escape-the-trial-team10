# verdict-interfaces Specification

## Purpose
Exposes the verdict to people and AI agents through a CLI command and an MCP tool with identical output.

## Requirements

### Requirement: CLI command
The system SHALL provide a command that takes an A/B test ID, an optional `--horizon` in days, an optional `--after-days` (days the shipped arm serves traffic after the stop, for money at stake), an optional `--replay <dir>`, an optional `--app <app id>`, an optional `--as-of YYYY-MM-DD` and an optional `--format json|card`, and prints the verdict to stdout with exit code 0, or an error with a non-zero exit code. `--as-of` SHALL be accepted only with `--replay`, and only when the bundle has no recording day or the date equals it: a replay holds the counts of its recording day, so judging it on another day would mix today's counts with other ages. Live reads always judge the test today.

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
- **WHEN** a user passes `--as-of 2026-12-20` with `--replay` on a bundle recorded on 2026-11-03
- **THEN** it prints an error naming both dates and exits non-zero

#### Scenario: As-of date on a live read
- **WHEN** a user passes `--as-of` without `--replay`
- **THEN** it prints an error saying that `--as-of` works only with `--replay` and exits non-zero

#### Scenario: Usage error in card format
- **WHEN** a user passes an invalid argument together with `--format card`
- **THEN** it prints `ERROR: <message>` and exits non-zero

### Requirement: MCP tool
The system SHALL provide a stdio MCP server with one tool `ab_test_verdict` that takes a test ID, an optional horizon in days, an optional `after_days`, an optional replay directory and an optional app ID, and returns the same JSON as the CLI. The tool description SHALL tell calling agents to run it before stopping a test or choosing a winner, to explain the verdict using only numbers from the JSON, and to pass `horizon` as the number of days the test goal names (for example "60-day revenue" → 60) or omit it when the goal names none. The server SHALL work when started from any working directory: the generated configuration sets `PYTHONPATH` to the repository, and the server reads `.env` from the repository root when its working directory has none.

#### Scenario: Same answer on both paths
- **WHEN** the CLI and the MCP tool run on the same test with the same inputs
- **THEN** their JSON outputs are identical

#### Scenario: Horizon from the goal
- **WHEN** an agent lists the tool
- **THEN** its description tells it to pass the number of days named in the test goal as `horizon`, and to omit `horizon` otherwise

#### Scenario: Started from another directory
- **WHEN** the MCP server runs with a working directory that has no `.env` and no copy of the code, using the generated configuration
- **THEN** it starts, and it reads the `.env` in the repository root

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
The system SHALL provide a Claude Code `PreToolUse` hook that runs before an agent ends an Adapty A/B test and decides from the verdict of that test. It SHALL cover the Adapty MCP tools `ab_tests_stop` and `ab_tests_replace` of any MCP server name, the MCP tool `placements_update`, and Bash commands that run `adapty ab-tests stop`, `adapty ab-tests:stop`, `adapty ab-tests replace` or `adapty ab-tests archive` (also through `npx`, with or without a version). A Bash command with several such calls SHALL be decided by the strictest of them. The hook SHALL never stop, start or change a test itself; it only lets the call through to the human (`ask`) or blocks it (`deny`), and its reason SHALL quote only values from the verdict JSON and the test's arms:
- the verdict cannot be produced (error) → `deny`: no stop without a verdict;
- `next_action` is `fix_test` (the test is unhealthy) → `deny`, naming the sample ratio mismatch or the dead arm;
- `next_action` is `come_back` → `deny`, naming the verdict, `come_back_on`, `cost_per_day`, `loss_if_ship_leader_now` and `chance_leader_is_wrong` when present;
- `next_action` is `ship_leader` and the chosen winner is another arm, or the stop shows other content (`--other`, `--no-content`, `another_flow_id_to_run`, `another_paywall_id_to_run`) or replaces the test → `deny`, naming the verdict leader, its `p2bb_expected` and what the call would show;
- `next_action` is `ship_leader` and the winner is the leader, or `ship_either` with any winner of the test, or the stop names nothing to show → `ask`, with the verdict summary, so a human confirms the irreversible stop;
- a Bash command that mentions `adapty`, `ab-tests` and a test-ending word (in any letter case) that the hook cannot parse into literal values: a test ID, winner or app ID with a shell expansion (`$`, backticks, braces, globs), a subcommand in a variable, or text inside a string the hook does not unwrap → `deny`: the hook cannot check what it cannot read. Calls inside `bash -c`, `sh -c` and `eval` strings are unwrapped and decided like plain calls, and the program name `adapty` matches in any letter case;
- `placements_update` → `ask`, because changing a placement's audiences can end a test running there.
These decisions are the `strict` mode. The guard SHALL also have an `ask` mode, in which every decision is `ask`: when `strict` would deny, the reason starts with a warning that the stop goes against the verdict (or that there is no verdict, or that the command cannot be checked) and carries the same facts. The mode SHALL come from the environment variable `VERDICT_GUARD_MODE` when it is set, otherwise from the `--mode` argument of the hook command (`--mode X` or `--mode=X`), otherwise `ask`; an unknown value SHALL mean `strict`. In `strict`, a deny reason SHALL tell the agent that the user can restart the session with `VERDICT_GUARD_MODE=ask` to confirm the stop themselves. Any failure of the hook itself (malformed input, a crash, a missing interpreter, a moved repository) SHALL block the call: the hook exits with code 2 or the hook configuration sets `onFailure: "block"`. The guard is optional: a project gets it only through `scripts/install_guard.sh <dir> [--mode ask|strict]` (default `ask`) or by adding the hook to its settings by hand. The guard catches an agent's mistakes and plain commands; it is not a sandbox against an agent that writes scripts on purpose, and the documentation SHALL say so.
Commands that cannot end a test SHALL pass through with no output. The hook SHALL read the test from a recorded bundle instead of Adapty when the environment variable `VERDICT_GUARD_REPLAY` lists a bundle (paths separated by the OS path separator) whose `ab-tests_get.json` has the stopped test's ID.

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

#### Scenario: A second stop in the same command
- **WHEN** a Bash command stops the synthetic test with the leader and then, after `&&`, stops it again with `annual_upfront`
- **THEN** the hook denies the command

#### Scenario: Other syntaxes and tools that end a test
- **WHEN** an agent runs `adapty ab-tests:stop …`, `npx -y adapty@latest ab-tests stop …`, `adapty ab-tests replace …`, or calls `mcp__subs__ab_tests_replace`, each with `annual_upfront` or a replacement while the verdict leader is `weekly_trial`
- **THEN** the hook denies each of them in `strict` mode

#### Scenario: Other content instead of the leader
- **WHEN** an agent stops the synthetic test with `--other` or `another_flow_id_to_run` while the verdict is `ship_leader`
- **THEN** the hook denies the call in `strict` mode

#### Scenario: A stop the hook cannot read
- **WHEN** an agent runs `c=stop; adapty ab-tests $c …` or `adapty ab-tests stop <id> --winner $W`
- **THEN** the hook denies it in `strict` mode and asks the human in `ask` mode, saying it cannot check the command

#### Scenario: A stop inside bash -c or in capitals
- **WHEN** an agent runs `bash -c "adapty ab-tests stop <synthetic id> --winner annual_upfront"` or `Adapty ab-tests stop <synthetic id> --winner annual_upfront`
- **THEN** the hook reads the call and denies it in `strict` mode against the verdict leader `weekly_trial`

#### Scenario: Placement update
- **WHEN** an agent calls `placements_update`
- **THEN** the hook asks the human and the reason says that changing audiences can end a running test

#### Scenario: Hook failure blocks
- **WHEN** the hook receives malformed input, or its Python environment is missing
- **THEN** the call is blocked, not let through

#### Scenario: Ask mode hands a disagreeing stop to the human
- **WHEN** the mode is `ask` and an agent stops the synthetic test at day 14 with winner `annual_upfront`
- **THEN** the hook answers `ask`, and the reason starts with a warning and names `weekly_trial` and `annual_upfront`

#### Scenario: The human sets the mode, not the command
- **WHEN** the hook command says `--mode strict` and `VERDICT_GUARD_MODE` is `ask`
- **THEN** the guard runs in `ask` mode

#### Scenario: Mode with an equals sign
- **WHEN** the hook command says `--mode=strict` and `VERDICT_GUARD_MODE` is not set
- **THEN** the guard runs in `strict` mode

#### Scenario: Unknown mode is strict
- **WHEN** `VERDICT_GUARD_MODE` is `off`
- **THEN** the guard runs in `strict` mode

#### Scenario: Other commands pass
- **WHEN** an agent runs any other Bash command or `adapty ab-tests get`
- **THEN** the hook prints nothing and exits 0

### Requirement: Decision card
The CLI SHALL accept `--format json` (default) or `--format card`. The card is a short text rendering of the same verdict for a person reading a terminal, in the style of experiment platforms' status lines. It SHALL use only values that appear in the verdict JSON, and SHALL contain:
- a status line: `FIX TEST` for `next_action` `fix_test`, followed by `srm_p` or the dead arm; `SHIP <leader>` for `next_action` `ship_leader`, `SHIP EITHER` for `ship_either`, `WAIT until <come_back_on>` for `come_back` with a date, `WAIT` without one; followed by the verdict, the reason when present and the `next_action_basis`;
- `p2bb_expected` next to `p2bb_raw` and the horizon they refer to (`at a <horizon_days>-day horizon`), and `maturity` as a fraction and a percentage of expected revenue received;
- for the leader, revenue per user: received, expected from trials, expected from renewals, expected total;
- when `money` is not `null`: `cost_per_day`, `loss_if_ship_leader_now`, `cost_until_come_back` when present, and `chance_leader_is_wrong`.
On an error the card SHALL be `ERROR: <message>` and the exit code non-zero. The stop guard's reason SHALL start with the same card joined into one line.

#### Scenario: Card for the synthetic trap
- **WHEN** a user runs the CLI with `--format card` on the synthetic test at day 14
- **THEN** the card starts with `SHIP weekly_trial` and contains `0.9999`, `raw 0.0`, `60-day horizon`, `$173.86` and `$0.3`

#### Scenario: Card for a test that is too early
- **WHEN** the verdict is `not_enough_data` with `come_back_on` 2027-01-05
- **THEN** the card starts with `WAIT until 2027-01-05` and has no money line

#### Scenario: Every number in the card comes from the JSON
- **WHEN** the card is rendered for any verdict
- **THEN** `eval/check_agent_text.py` finds every number of the card in the verdict JSON

#### Scenario: Card error
- **WHEN** the verdict cannot be produced
- **THEN** the card is `ERROR: <message>` and the CLI exits non-zero

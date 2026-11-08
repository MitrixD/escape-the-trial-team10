# Proposal

## Why

Ten independent reviewers and a judge checked Verdict Agent on 8 Nov 2026 (`research/product-review-2026-11-08.md` outside the repo, summary in `docs/ai-log-full.md`). The arithmetic is honest and the eval reproduces, but the tool is statistically overconfident and can flip its verdict silently, and the stop guard fails open and is easy to bypass. A false `confirmed` and an unguarded stop are exactly the risks the product exists to prevent, so they are fixed before the project is left as is. What cannot be fixed with the data available today goes to an honest "Known limitations" section.

## What Changes

- **Stop guard fails closed and sees every way to end a test.** Any failure in the hook blocks the call; the repo's hook without `.venv` still blocks test-ending commands; every stop in a chained command is checked; `ab-tests:stop`, `replace`, `archive`, MCP `ab_tests_replace` and `placements_update` are guarded; a command that mentions a test-ending subcommand the guard cannot parse goes to the human (`ask`) or is denied (`strict`); a stop that ships other content (`--other`, `--no-content`, `another_*_id_to_run`) is treated as not shipping the leader. The README stops promising that a determined agent cannot get around it.
- **Uncertainty of pending trials is counted.** Pseudo-users of a trial group convert or not (exact mean, Bernoulli spread) instead of each getting the mean; for three arms `p2bb_expected` is the probability that the leader is the best of all arms.
- **No silent flips.** Draft tests are rejected; stopped tests use their real running period; `--as-of` works only on replay and only on the recording day; a test older than its horizon is judged as past it, with a warning; the card names the horizon; basis `horizon` only after the horizon has passed; the come-back date uses the traffic of the arm that lacks users.
- **Calibration does not degrade silently.** Trials without any trial→paid rate give `not_enough_data` with reason `no_calibration`; products whose period (for example annual or lifetime) is not shorter than the horizon get no expected renewals; a product whose trial length is unknown but whose test funnel shows trials keeps 7 days; converted trial users are at least as old as the trial; the share of users still in trial is counted from all trial starts.
- **Data path:** replay serves paywall tests; the history window of recorded bundles matches live reads; `.env` values may carry inline comments; the MCP server and `setup.sh` work from any folder.
- **Eval honesty:** the agent-text check also checks the leader and negations; replay calibration uses the window before the test start; new eval cells show per-product calibration skew and front-loaded arrival, with their numbers in `eval/RESULTS.md`; dead links to spike output files are replaced by commands.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ab-test-verdict`: expected revenue (trial spread, renewals by period), horizon, verdict rules (missing trial rate), come-back date, next action (horizon basis), three-arm P2BB, decision card horizon.
- `adapty-test-data`: test state, live user ages, replay of paywall tests, history window.
- `verdict-interfaces`: CLI `--as-of`, stop guard coverage and fail-closed behaviour, MCP server start from any folder.

## Impact

Code in `verdict_agent/` (verdict, estimator, stats, calibration, live, guard, card, cli, service), `scripts/setup.sh`, `scripts/install_guard.sh`, `scripts/record_fixtures.sh`, `.claude/settings.json`, `.mcp.json.example`, `eval/`. The JSON contract gains no fields; `p2bb_expected` changes meaning only for three arms. Eval numbers will move and are re-run and reported honestly, without tuning thresholds.

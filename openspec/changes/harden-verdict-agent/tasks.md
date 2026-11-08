# Tasks

Every task starts with a failing test (openspec/config.yaml). Thresholds are not changed to make numbers look better.

## 1. Stop guard

- [x] 1.1 Failing tests, then: all stops and replaces in one Bash command are collected and the strictest decision wins; `ab-tests:stop`, `replace`, `archive`, `npx -y adapty@x`; unreadable test-ending commands deny (strict) or ask; `--other`, `--no-content`, `another_*_id_to_run`, MCP `ab_tests_replace` count as showing other content; `placements_update` asks; `--mode=X`; `main` fails closed
- [x] 1.2 Hook configuration: exit 2 when the interpreter is missing (`install_guard.sh`), the repo's `.claude/settings.json` blocks test-ending Bash commands without `.venv`, matchers for any MCP server name; verify by piping JSON into the configured commands

## 2. Test state, as-of, horizon

- [x] 2.1 Failing tests, then: draft tests rejected; stopped tests use the running period for traffic and ages
- [x] 2.2 Failing tests, then: `--as-of` only with `--replay` and only on the recording day; usage errors in card format print `ERROR:`
- [x] 2.3 Failing tests, then: a horizon shorter than the test's age is rejected; `horizon_reached` is `as_of ≥ start + horizon`; a come-back date on the judging day before the horizon moves 7 days; the card names the horizon

## 3. Statistics

- [x] 3.1 Failing tests, then: Bernoulli pseudo-users for trial groups (exact mean, the scenario from the spec gives `p2bb_expected` below 0.95)
- [x] 3.2 Failing tests, then: P(best) for three arms with a fixed seed
- [x] 3.3 Failing tests, then: come-back date at the lagging arm's traffic

## 4. Calibration and live data

- [x] 4.1 Failing tests, then: catalog periods in the calibration, no renewals for annual (horizon under 365) and lifetime actives
- [x] 4.2 Failing tests, then: trials without any rate give `no_calibration`; trial length 0 with trials in the funnel uses 7 days and warns
- [x] 4.3 Failing tests, then: converted trial users at least `t` days old; pending share from all trial starts
- [x] 4.4 Failing tests, then: replay of paywall funnels; inline comments in `.env`; `record_fixtures.sh` history window and exact company check

## 5. Interfaces and setup

- [x] 5.1 `setup.sh` resolves `--guard`/`--mcp` paths before `cd` and survives `#` in paths; `.mcp.json` from `setup.sh` and `.mcp.json.example` sets `PYTHONPATH`; verify the MCP server starts from `/`
- [x] 5.2 The card tolerates missing fields; MCP description mentions the horizon caveat

## 6. Eval

- [x] 6.1 Failing tests, then: `check_agent_text` checks the stated leader and catches "not confirmed" on a `confirmed` verdict
- [x] 6.2 Replay serves calibration from the window before the test start; regenerate the committed synthetic bundle if its numbers change
- [x] 6.3 Two adverse cells in `eval/calibration_robustness.py` (one product's renewals off by 30%, front-loaded arrival); dead links to spike output files replaced by commands
- [x] 6.4 Re-run `eval/verdict_eval.py` and `eval/calibration_robustness.py`; update `eval/RESULTS.md`, README numbers and the card picture with the new numbers, as they are

## 7. Documents and review

- [x] 7.1 README: glossary fixed (`p2bb_expected` is a normal approximation, not Adapty's model), guard described as a guard against mistakes with a recommendation for permission rules, "Known limitations" under a spoiler with what remains and why; README.ru; AI_LOG and the full log
- [ ] 7.2 Independent review on Fable 5.1 of the whole branch; fix what it confirms
- [ ] 7.3 Full suite with `VERDICT_DATASET`, `openspec validate --all --strict`, archive the change

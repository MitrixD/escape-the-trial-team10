# Design

## Context

The 8 Nov review (ten reviewers and a judge, summary in `docs/ai-log-full.md`) confirmed 22 issues. This change fixes every one that can be fixed with the data the tool reads today. Two kinds stay open and go to README "Known limitations": those that need a real customer app to measure (how Adapty's install-dated LTV differs from subscription age, per-product revenue inside an arm, segment filters on funnel and analytics) and those that need a new model (calibration from the arm's own finished trials, a Bayesian model like Adapty's).

## Goals / Non-Goals

**Goals:** no silent flip of the verdict; confidence that includes the uncertainty we can measure; a guard that blocks on failure and sees every plain way to end a test; documents that do not promise more than the code does.

**Non-Goals:** a sandbox against an agent that deliberately writes scripts to get around the guard; a new statistical model; new Adapty API calls beyond the current budget.

## Decisions

**1. Bernoulli pseudo-users for trial groups.** A trial group of `n` users with conversion `c` and gain `g` becomes `k = floor(c·n)` users with value `received + g`, one user with `received + (c·n − k)·g`, and the rest with `received`. The mean stays exactly `received + c·g`; the spread is the spread of the conversion outcome. This keeps the pseudo-user design (one list of values per arm) and the existing `p2bb`. *Alternative:* analytic per-group variance — cleaner, but every downstream function (`diff_ci`, `diff_mean_se`, money) works on value lists.

**2. P(best) for three arms.** With three arms, `p2bb_expected` and `p2bb_raw` are estimated by drawing each arm's mean from a normal distribution with its mean and standard error, 20,000 draws with a fixed seed, and counting how often the leader is the largest. Two arms keep the closed form, so existing numbers do not move.

**3. Renewals by catalog period.** `products list` gives `period` (weekly, monthly, two_months, trimonthly, semiannual, annual, lifetime). An active user of a product whose period in days is not shorter than the horizon gets future revenue `min(0, L(h) − L(a))`, a lifetime product always: a rising curve there comes from install-dated cohorts, not renewals. Trial users still use the curve, because their first payment is in it.

**4. Missing trial rate is `no_calibration`.** If an arm has `trial` groups and neither their product nor the app has a trial→paid rate, the verdict is `not_enough_data` with reason `no_calibration`, instead of valuing trials at $0.

**5. Test state and dates.** `started_at` null → `VerdictError`. With `stopped_at`, the running period is `start … stop`; traffic is users / running days; ages get an offset of the days since the stop. `--as-of` is a CLI rule: only with `--replay`, and only on the recording day (or when the bundle has none). `run_live(today=…)` keeps its parameter for the eval, which builds bundles whose recording day is the judging day.

**6. Horizon.** A test older than its horizon is judged as past it: future revenue is zero, the next action has basis `horizon`, and a warning says that received revenue covers more days than the horizon. A first version rejected such a horizon; the final review showed that this made every overrun or stopped test impossible to judge on its goal horizon. The card prints `at a N-day horizon`. `horizon_reached` is `as_of ≥ start + horizon`. When the come-back date comes out as the judging day before the horizon, it is pushed 7 days.

**7. Come-back date by the lagging arm.** Missing users are counted for the smaller of the two compared arms, and days at that arm's own daily traffic.

**8. Live ages.** Converted trial users are spread over ages from `t` to `D` (they paid after the trial); pending trials are `min(unconverted, round(starts · min(1, t/D)))`; an unknown trial length (0) with trials in the funnel uses 7 days and logs a warning.

**9. Guard: fail closed, wider net, honest wording.** `main` runs entirely under `try` and answers `deny` on any exception; the hook command exits 2 when the interpreter is missing, so Claude Code blocks; the repo's `.claude/settings.json`, when `.venv` is missing, blocks Bash commands that mention `ab-tests` with a test-ending word and lets others pass. The parser collects every `adapty … ab-tests[: ]stop|replace|archive` occurrence (also `npx [-y] adapty[@version]`); any command mentioning `adapty`, `ab-tests` and a test-ending word that yields no parsed call, or a call whose test ID, winner or app ID holds a shell expansion, is "unreadable" → deny (strict) or ask. Program and subcommand names match in any letter case (macOS file systems run `Adapty` as `adapty`). `--other`, `--no-content`, `another_*_id_to_run` and `replace` are "shows other content". MCP matchers become `mcp__.*__ab_tests_(stop|replace)` and `mcp__.*__placements_update`. `--mode=X` is parsed. The README calls the guard a guard against mistakes, not a sandbox, and recommends Claude Code permission rules (`ask` or `deny` on the Adapty test-ending tools) for teams that need a hard block.

**10. Eval honesty.** Replay serves calibration only from the window before the test start, like live. `check_agent_text` also checks that the stated leader is the verdict leader and fails on "not confirmed" for a `confirmed` verdict. `eval/calibration_robustness.py` gets two adverse cells (renewals of one product off by 30%; all users arriving in the first 3 days) whose numbers are reported as they are.

**11. Small fixes.** Replay finds `paywall_id` funnels; `record_fixtures.sh` uses the live history window and the exact company check; inline `#` comments in `.env` are dropped; `setup.sh` resolves paths before `cd` and escapes them; `.mcp.json` sets `PYTHONPATH`; dead links to spike output files become commands.

## Risks / Trade-offs

- [Eval numbers move] → re-run and reported as they are; thresholds unchanged.
- [The guard blocks a harmless `echo adapty ab-tests stop`] → acceptable: a false block costs one confirmation; a false pass costs a stopped test.
- [Period rule hides real refunds or upgrades of annual plans] → keeps refunds (negative change) and is documented.

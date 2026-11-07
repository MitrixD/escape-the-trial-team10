# Tasks

How to use this list: groups are tracks. "Needs" names the groups or tasks that must be merged first; everything else can run in parallel. Claim a task by putting your name after it in your branch's first commit (for example `(Maxim)`) and open one PR per task or per small group. Interfaces are fixed in design.md → "Interfaces"; if you need a module another track has not merged yet, stub it with the same signature. Every task that adds behaviour starts with a failing test (openspec/config.yaml). References: the spike `eval/ab_verdict_eval.py` for `p2bb` and the estimator's mean; the first implementation on `feature/verdict-agent` for the CLI wrapper, funnel parsing and fixtures. The offline dataset (`https://github.com/kpotehin/adapty-seed-data-hack`, `data/offline`, exported as `VERDICT_DATASET`) is used only in group 6.

Parallel start: after group 1, track A (groups 2–3) and track C (group 4) run at the same time. Group 4.1 (recording live responses) is the first thing to do on the Adapty side, because track A's calibration tests need those recordings.

## 1. Foundation — needs nothing, blocks everything

- [x] 1.1 Create `verdict_agent/`, `tests/`, `requirements.txt` (`pytest==9.2.0`, `mcp==2.3.0`), `pytest.ini` with marker `dataset`, `tests/conftest.py` with a session fixture `dataset_path()` that skips when `VERDICT_DATASET` is unset, `.env.example` with empty `ADAPTY_APP_ID`, `ADAPTY_EXPECTED_COMPANY`, `ADAPTY_SECRET_KEY`, `VERDICT_DATASET`, and `.gitignore` entries `*.pem *.key *.p8 *.p12 .venv/ __pycache__/`; verify `pytest` runs and `git check-ignore .env` prints `.env`
- [x] 1.2 Write `verdict_agent/model.py` with `Group`, `Arm` (property `users`), `TestData` and `Calibration` exactly as in design.md → Interfaces; verify a test constructs each and `Arm.users` sums group sizes

## 2. Track A — statistics and calibration (needs 1; 2.2 needs 4.1 recordings)

- [x] 2.1 Write failing tests, then `verdict_agent/stats.py`: `p2bb` (must equal the spike's `p2bb` on a fixed sample), `diff_ci` (95% interval of a difference in means), `users_needed` (per-arm sample size for a given delta and sd); verify the tests pass
- [x] 2.2 Write failing tests on the recorded `conversion` and `ltv` responses of the test app, then `verdict_agent/calibration.py` `build_from_adapty` and `product_map_from_catalog`: trial→paid per product, renewal value curve per product up to the horizon from `ltv`, trial length from the curve, product-key normalisation (store key and UUID → one key), app-wide fallback, `source` `product | app | none`, `expected(status, product, age, horizon)` with the formulas from design.md → Decision 2, JSON save/load; verify the tests pass, an unknown product reports `app`, and empty responses report `none`

## 3. Track A — estimator and verdict (needs 2)

- [x] 3.1 Write failing tests, then `verdict_agent/estimator.py`: pending trials raise expected revenue above received; an up-front-only arm has renewals ≤ 0; group mean equals a per-user computation with the same calibration within $0.01; zero users → zeros; verify the tests pass
- [x] 3.2 Write failing tests for every scenario under "Verdict rules", "Raw P2BB shown next to expected P2BB", "Probabilities never round up into confirmed" and "At least two arms" in specs/ab-test-verdict, then implement `build_verdict` in `verdict_agent/verdict.py` with the four verdicts and `reason`; verify the tests pass
- [x] 3.3 Write failing tests for the horizon parameter (60 when omitted, error below 1, the goal is not parsed) and for `come_back_on` (min-events date, pending-revenue date, underpowered date via `users_needed`, cap at horizon, `null` when decided), then implement; verify the tests pass
- [x] 3.4 Write `verdict_agent/schema.json` per "Output contract" and a stdlib checker test that every verdict produced in tests validates; verify it passes

## 4. Track C — Adapty live data (4.1, 4.5 need 1; 4.4 needs 2.2, 3.2)

- [x] 4.1 Write `scripts/record_fixtures.sh` that runs, with `sleep 1` between calls and `--json`: `auth whoami` (redacted to the company field), `ab-tests get`, `ab-tests metrics total`, `products list`, `analytics funnel` per arm (filters `flow_id` and `placement_id`, `--group-by store_product_id`), `analytics conversion --conversion trial-paid --group-by store_product_id`, `analytics cohort --group-by store_product_id` over renewal periods, `analytics ltv --group-by store_product_id`, with `--date-to` at the test start where the command allows it; never `apps get`; run it once on the live Onboarding test and once on Main; verify ≤ 10 calls per test, no 429, and a grep of `tests/fixtures/live/**` finds no `@`, token or secret. Record in README which of `cohort` and `ltv` returned per-product rows
- [x] 4.2 Write failing tests with a fake runner, then `verdict_agent/adapty_cli.py`: read-only allowlist with `apps get` denied, ≥ 0.5 s spacing, exit 4 → `RateLimited(retry_after)` and no further calls, non-JSON output → `CliError`, `check_account` raises `WrongAccount` without printing any value, `replay_runner(dir)` that serves recorded JSON by command and raises a clear error naming a missing command; verify the tests pass with no network
- [x] 4.3 Write failing tests on the recorded fixtures, then `live_test` and `live_calibration` in `verdict_agent/live.py`: per-product sums equal metrics totals (users 285/254, trials 71/66), App Store and Play keys merge through the recorded product catalog with no app-specific mapping in code, converted trials go to `active`, trials older than their product's trial length become `ended`, calibration built from the recorded analytics through `build_from_adapty`; verify the tests pass
- [x] 4.4 Implement `run_live(test_id, today, horizon, replay)`: read `.env`, `check_account` before any data read (skipped on replay), `live_test`, `live_calibration`, `build_verdict`; verify an end-to-end test on the Onboarding recordings makes ≤ 10 wrapper calls and the output validates against the schema
- [x] 4.5 Time-boxed (2 h) investigation, no product code: which per-user data Adapty can give for a test's users (Server-side API profile reads by `customer_user_id`, Export Analytics breakdowns, S3/GCS export), at what call cost and within the hackathon rules; verify a note `docs/per-user-data.md` lists each source, what it returns, its cost in calls, and a recommendation on whether a per-user estimator is feasible after the hackathon

## 5. Interfaces (needs 3, 4)

- [x] 5.1 Write failing tests, then `verdict_agent/service.py` and `verdict_agent/cli.py` (`<id> [--horizon N] [--replay DIR]`): JSON on stdout and exit 0; any error → `{"error": ...}` and exit 1 with no traceback and no `.env`/account values; verify the tests pass
- [x] 5.2 Write failing tests, then `verdict_agent/mcp_server.py` with one tool `ab_test_verdict(ab_test_id, horizon, replay)` whose description tells agents to call it before stopping a test, to use only JSON numbers, and states the units; verify the handler returns the same JSON as the service
- [x] 5.3 Run `python -m verdict_agent.cli <onboarding test id>` once against Adapty; verify valid JSON and ≤ 10 read-only calls; save the output and the responses as the replay bundle after a secret grep

## 6. Eval (needs 5.1; dataset tests only)

- [x] 6.1 Write `eval/make_replay.py`: from the offline dataset, for a test name, day N and traffic, sample users like the spike and write an Adapty-shaped replay bundle (`ab-tests get`, `metrics total`, `funnel` per arm by product, `conversion`, `cohort`, `ltv` built from users outside the test up to day N); verify a test that the bundle validates against the recorded live shapes and that the verdict on it runs through `--replay`
- [x] 6.2 Write `eval/verdict_eval.py`: Main, Onboarding, Settings and the synthetic test × days 1, 3, 7, 14, 21, 28 × 30 and 100 users/day × 150 reps (seed 7) through replay bundles, scored against 60-day truth; print wrong-confirmed, right-confirmed, raw-wrong, and the verdict distribution; verify the synthetic test has wrong-confirmed 0% and raw-wrong 100% at day 14 (report honestly if not, do not tune) and append the tables with their limits to `eval/RESULTS.md`, marking the first implementation's tables as computed with per-user calibration
- [x] 6.3 Move `eval/synthetic_test/` onto the replay path: `make_test.py` keeps producing the dataset, `run_synth.py` calls `make_replay` and the CLI; verify `eval/synthetic_test/RESULTS.md` is regenerated with the new numbers

## 7. Delivery (needs 5, 6)

- [ ] 7.1 Write README: what it does and for whom (the two-piggy-bank story), how to run from a clean clone (Adapty CLI login, `.env`, replay bundle for the no-network path), architecture, eval numbers with limits, next steps (the full Non-Goals list in design.md: money at stake, next step advice, validity checks, guardrails, segments, UI, per-arm calibration, lognormal P2BB, demo script and agent-text check, `doctor`, per-user estimator, spread inside a group), who did what, what was made before the hackathon core; verify a clean clone runs the replay command from README alone
- [ ] 7.2 Run the full test suite with `VERDICT_DATASET` exported and `openspec validate add-verdict-agent --strict`; verify both pass

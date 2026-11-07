# Tasks

How to use this list: groups are tracks. "Needs" names the groups or tasks that must be merged first; everything else can run in parallel. Claim a task by putting your name after it in your branch's first commit (for example `(Maxim)`) and open one PR per task or per small group. Interfaces are fixed in design.md → "Interfaces"; if you need a module another track has not merged yet, stub it with the same signature. Every task that adds behaviour starts with a failing test (openspec/config.yaml). The spike reference implementation is `eval/ab_verdict_eval.py`; the dataset comes from `https://github.com/kpotehin/adapty-seed-data-hack` (`data/offline`), exported as `VERDICT_DATASET`.

Parallel start: after group 1, track A (groups 2–3), track C (group 5, tasks 5.1–5.3) and the docs skeleton can run at the same time. Track B (group 4) starts after 2.1. Track D (group 6) starts after 2.2 and 3.2.

## 1. Foundation — needs nothing, blocks everything

- [ ] 1.1 Create `verdict_agent/`, `tests/`, `requirements.txt` (`pytest==9.2.0`, `mcp==2.3.0`), `pytest.ini` with marker `dataset`, `tests/conftest.py` with a session fixture `dataset_path()` that skips when `VERDICT_DATASET` is unset, `.env.example` with empty `LUMEN_APP_ID`, `ADAPTY_EXPECTED_COMPANY`, `VERDICT_DATASET`, and `.gitignore` entries `*.pem *.key *.p8 *.p12 .venv/ __pycache__/`; verify `pytest` runs and `git check-ignore .env` prints `.env`
- [ ] 1.2 Write `verdict_agent/model.py` with `Group`, `Arm` (property `users`) and `TestData` exactly as in design.md → Interfaces; verify a test constructs each and `Arm.users` sums group sizes

## 2. Track A — statistics and calibration (needs 1)

- [ ] 2.1 Write failing tests, then `verdict_agent/stats.py`: `p2bb` (must equal the spike's `p2bb` on a fixed sample), `two_prop_p`, `welch_p`, `diff_in_diff_p`, `bonferroni` (`[0.03, 0.5]` → `[0.06, 1.0]`); verify the tests pass
- [ ] 2.2 Write a failing dataset test that `build_offline(users, "Settings: upgrade vs lifetime anchor", 60)` equals the spike's `calibrate()` on users outside that test, then implement `verdict_agent/calibration.py` with the fallback chain and JSON save/load; verify the test passes and an unknown product falls back by status

## 3. Track A — estimator and verdict (needs 2)

- [ ] 3.1 Write failing tests, then `verdict_agent/estimator.py`: pending trials raise expected revenue above received; on Settings day 14 at 100 users/day (seed 7) the group mean equals the spike's per-user `predict()` mean within $0.01; zero users → zeros; verify the tests pass
- [ ] 3.2 Write failing tests for every scenario under "Verdict rules", "Raw P2BB shown next to expected P2BB", "At least two arms" and "Probabilities never round up into confirmed" in specs/ab-test-verdict, then implement `build_verdict` in `verdict_agent/verdict.py`; verify the tests pass
- [ ] 3.3 Write failing tests for horizon resolution (parameter > goal capped at 120 > 60, range 1–120, `horizon_source`), money at stake (equal arms → 0), `come_back_on` rules and next-step types (design.md → Decisions), then implement; verify the tests pass
- [ ] 3.4 Write `verdict_agent/schema.json` and a stdlib checker test that every verdict produced in tests validates; verify it passes

## 4. Track B — guardrails and segments (needs 2.1; 4.3 needs 3.2)

- [ ] 4.1 Write failing tests for the two guardrail scenarios in specs/ab-test-verdict (per user vs per payer; real problem keeps the verdict), then implement `warnings_for` in `verdict_agent/guardrails.py`; verify they pass
- [ ] 4.2 Write failing tests that Settings iOS is not reported after Bonferroni (dataset) and that 20 runs × 20 random null attributes find at most one segment, then implement `check_segments` in `verdict_agent/segments.py`; verify they pass
- [ ] 4.3 Wire warnings into `build_verdict`: `next_step.watch` lists every warning metric, `alternative` targets the first `worse` one, the verdict never changes; verify a test compares the verdict with and without warnings

## 5. Track C — Adapty live data (5.1–5.3 need 1; 5.4 needs 2.2, 3.2)

- [ ] 5.1 Write `scripts/record_fixtures.sh` that runs only `auth whoami`, `ab-tests get`, `ab-tests metrics total`, `analytics funnel` per arm (filters `flow_id` and `placement_id`, `--group-by store_product_id`) and `analytics conversion trial-paid` with `sleep 1` between calls, never `apps get`, and redacts `whoami`; run it once on the live Onboarding test; verify ≤ 10 calls, no 429, and a grep of `tests/fixtures/live/*.json` finds no `@`, token or secret
- [ ] 5.2 Write failing tests with a fake runner, then `verdict_agent/adapty_cli.py`: read-only allowlist with `apps get` denied, ≥ 0.5 s spacing, any exit 4 is a sticky stop (`RateLimited`), non-JSON output → `CliError`, `check_account` raises `WrongAccount` without printing any value; verify the tests pass with no network
- [ ] 5.3 Write failing tests on the recorded fixtures, then `live_test` and `expire_trials` in `verdict_agent/live.py`: per-product sums equal metrics totals (users 285/254, trials 71/66), converted trials go to `active` (see specs/adapty-test-data), trials older than their product's trial length become `ended`; verify the tests pass
- [ ] 5.4 Implement `run_live`: check the horizon, read `.env`, `check_account` before any data read, calibration from the offline dataset excluding the offline test with the live title, `warnings_for`, `build_verdict`; verify an end-to-end test on fixtures makes exactly 5 calls and the output validates against the schema

## 6. Track D — offline mode (needs 2.2, 3.2)

- [ ] 6.1 Write failing dataset tests, then `load_users`, `trial_days_from` and `offline_test` in `verdict_agent/offline.py`: sampling matches the spike for both arms, two arms of 1,400 users for Settings day 14 at 100/day, counts use only events up to each user's age; verify they pass
- [ ] 6.2 Implement `run_offline` (validates day ≥ 1, traffic ≥ 1, day ≤ horizon; calibration built once per test and horizon) and save day-14 outputs for Onboarding, Settings and Main as fixtures written only with `VERDICT_WRITE_FIXTURES=1`; verify a default test compares fresh output with the fixtures

## 7. Interfaces (needs 3, 5.4, 6)

- [ ] 7.1 Write failing tests, then `verdict_agent/service.py` and `verdict_agent/cli.py` (`live <id> [--horizon]`, `offline "<name>" [--day] [--traffic] [--horizon]`): JSON on stdout and exit 0; any error → `{"error": ...}` and exit 1 with no traceback and no `.env`/account values (specs/verdict-interfaces → Safe errors); verify the tests pass
- [ ] 7.2 Write failing tests, then `verdict_agent/mcp_server.py` with one tool `ab_test_verdict` whose description tells agents to call it before stopping a test, to use only JSON numbers, to say live vs offline, and states the units (spec "Units in the tool description"); verify the handler returns the same JSON as the service
- [ ] 7.3 Run `python -m verdict_agent.cli live <onboarding test id>` once against Adapty; verify valid JSON with `source: live`, ≤ 15 read-only calls, and save it as a fixture after a secret grep

## 8. Eval (needs 6)

- [ ] 8.1 Write `eval/verdict_eval.py`: 3 tests × days 1, 3, 7, 14, 21, 28 × 30 and 100 users/day × 150 reps (seed 7) against 60-day truth; print wrong-confirmed, right-confirmed, early-when-raw-wrong and the verdict distribution; verify Settings day 14 at 100/day has wrong-confirmed ≤ 5% (report honestly if not, do not tune) and append the tables with their limits to `eval/RESULTS.md`
- [ ] 8.2 Add the noise-segment eval (20 runs × 20 random attributes); verify ≤ 1 segment found and record it in `eval/RESULTS.md`

## 9. Delivery (needs 7, 8)

- [ ] 9.1 Write `eval/check_agent_text.py` with a unit test; ask Claude three times through the MCP tool (live Onboarding, offline Settings day 14, offline Main day 14) and check every number in each answer exists in the JSON and the verdict word matches; verify results are recorded in `AI_LOG.md`
- [ ] 9.2 Write README: what it does, for whom, how to run from a clean clone (dataset repo, Adapty CLI), what is live vs offline, architecture, eval numbers with limits, next steps, who did what, what was made before the hackathon core; verify a clean clone runs the offline command from README alone
- [ ] 9.3 Write `docs/demo-script.md` (≤ 3 minutes, LIVE and OFFLINE parts marked, numbers from `eval/RESULTS.md`); verify a timed read-through
- [ ] 9.4 Run the full test suite with `VERDICT_DATASET` exported and `openspec validate add-verdict-agent --strict`; verify both pass

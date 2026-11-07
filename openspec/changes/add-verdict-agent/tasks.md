# Tasks

## 1. Setup

- [ ] 1.1 Create `verdict_agent/`, `tests/`, `requirements.txt` (`pytest`, `mcp`) and a README stub with run instructions; verify `python -m pytest` runs and reports 0 tests
- [ ] 1.2 Move the spike eval from `../eval/` into `eval/` unchanged and add a README section declaring it as made on 7 Nov; verify `python eval/ab_verdict_eval.py <dataset> 60` reproduces the Settings numbers in `eval/RESULTS.md`
- [ ] 1.3 Add `.env.example` (empty) and extend `.gitignore` with `*.pem *.key *.p8 *.p12`; verify `git check-ignore .env` prints `.env`

## 2. Statistics and calibration

- [ ] 2.1 Write failing tests for `p2bb`, two-proportion test, Welch test and Bonferroni, then implement `stats.py`; verify tests pass and `p2bb` matches the spike on a fixed sample
- [ ] 2.2 Write a failing test that the calibration table built from the offline dataset equals the spike's `calibrate()` output for test Settings, then implement `calibration.py` with save/load to JSON; verify the test passes

## 3. Estimator from groups

- [ ] 3.1 Write a failing test: expected revenue per user from groups equals the spike's per-user mean within $0.01 on Settings day 14, then implement `estimator.py`; verify it passes
- [ ] 3.2 Write a failing test that pending trials raise expected revenue above received (66 trials, $0 received), then make it pass; verify the trial and renewal parts are reported separately

## 4. Verdict rules

- [ ] 4.1 Write failing tests for each verdict scenario in `specs/ab-test-verdict` (not enough data, confident before maturity, immature and unsure, mature and unsure), then implement `verdict.py`; verify all pass
- [ ] 4.2 Write failing tests for horizon from goal, money at stake (equal arms → 0) and come-back dates, then implement; verify they pass
- [ ] 4.3 Write failing tests for next-step types per verdict, then implement; verify they pass
- [ ] 4.4 Write `schema.json` and a test that every verdict produced in tests validates against it; verify it passes

## 5. Guardrails and segments

- [ ] 5.1 Write failing tests for the refund per user vs per payer scenario and the real-problem scenario, then implement `guardrails.py`; verify the verdict is unchanged in both
- [ ] 5.2 Write a failing test that Settings iOS is not reported (corrected p ≈ 1.0) and random segments are rejected, then implement `segments.py`; verify both pass

## 6. Offline mode

- [ ] 6.1 Write a failing test that offline groups for Settings as of day 14 at 100 users/day reproduce the spike's sampled counts, then implement `offline.py`; verify it passes
- [ ] 6.2 Run the verdict offline on Onboarding, Settings and Main at day 14; verify the outputs are `source: offline` and record them as fixtures

## 7. Live data

- [ ] 7.1 Write tests for `adapty_cli.py` with recorded CLI responses: only read commands allowed, ≥ 0.5 s spacing, 429 → error with wait time; then implement; verify tests pass without network
- [ ] 7.2 Check live: `adapty auth whoami` and `analytics conversion trial-paid --group-by store_product_id` on Lumen; record whether live calibration works and save the responses as fixtures; verify a note in README says which calibration source the demo uses
- [ ] 7.3 Write a failing test mapping the recorded Onboarding responses to arm groups (285 and 254 users, 71 and 66 trials), then implement `live.py`; verify it passes
- [ ] 7.4 Run the live verdict on the Onboarding test once; verify a valid JSON with `source: live` and fewer than 15 Adapty calls in the log

## 8. Interfaces

- [ ] 8.1 Write a failing test for `cli.py`: prints the verdict JSON and exits 0; unknown ID → JSON error and non-zero; then implement; verify it passes
- [ ] 8.2 Implement `mcp_server.py` with one tool and the agent instructions in its description; verify a test calls the tool handler and gets the same JSON as the CLI
- [ ] 8.3 Register the MCP server in a local Claude Code config and ask Claude for a verdict on Onboarding; verify the answer quotes only numbers from the JSON and save the transcript to `AI_LOG.md`

## 9. Eval

- [ ] 9.1 Write `eval/verdict_eval.py` that runs the verdict function offline on days 1–28 at 30 and 100 users/day against 60-day truth; verify it prints wrong-confirmed, right-confirmed and early-when-raw-wrong rates for the three tests and save them to `eval/RESULTS.md`
- [ ] 9.2 Add the noise-segment eval (20 random segments × 20 runs); verify at most one false segment across runs
- [ ] 9.3 Check three recorded agent answers: every number in the text exists in the JSON and the stated verdict matches `verdict`; verify results are in `AI_LOG.md`

## 10. Delivery

- [ ] 10.1 Finish README: what it does, for whom, how to run (live and offline), what is real and what is offline, architecture, eval numbers with their limits, next steps, who did what; verify a clean clone runs the offline demo from README alone
- [ ] 10.2 Write the 3-minute demo script with the live and offline parts marked; verify a dry run fits in 3 minutes
- [ ] 10.3 Run `openspec validate add-verdict-agent --strict` and the full test suite; verify both pass

# Proposal

## Why

Adapty's raw P2BB (dashboard, CLI, MCP) counts only revenue already received. When one arm earns up front (annual, lifetime) and the other earns later (trial, then weekly or monthly renewals), raw P2BB confidently picks the up-front arm, and the error grows with traffic instead of fading: every day brings new users whose renewals have not started. On a synthetic Lumen test built from real dataset transactions, raw P2BB is ≥ 99.9% sure of the wrong arm on every day from 3 to 60, while the 60-day truth favours the trial arm $5.88 to $4.32 per user (`eval/synthetic_test/RESULTS.md`). AI agents are most exposed: Predicted P2BB is not available in CLI or MCP, and the `ab-tests` skill does not read results, so an agent asked whether a test can be stopped sees only the raw `probability` from `ab-tests metrics total`. Full reasoning: `docs/2026-11-07-verdict-agent-design.md`.

## What Changes

- New read-only tool that takes an Adapty A/B test ID and returns a verdict: `not_enough_data`, `keep_running`, `confirmed` or `tie`, with the leader, P2BB on expected revenue next to raw P2BB, revenue maturity and a come-back date.
- Expected revenue per arm = received + expected from pending trials + expected from future renewals, computed from per-arm, per-product counts and a calibration table built from the app's own history in Adapty (trial→paid conversion and renewal revenue per product). The horizon in days is a call parameter. No external datasets at run time.
- Works for any Adapty app: the app ID comes from `ADAPTY_APP_ID` in `.env` or from the call, products are mapped through the app's own catalog, and calibration comes from that app's history. Lumen is only the test app.
- Money at stake and a typed next step: the cost of one more test day, the expected loss of shipping the leader now, the cost of waiting until the come-back date and the chance the leader is wrong, in USD for the test's traffic; `next_action` is `ship_leader`, `ship_either` or `come_back`, and may say `ship_leader` on money grounds while the verdict is still `keep_running`. The spike `eval/money_at_stake.py` showed that waiting a fixed 14 days can cost more than stopping on the verdict when the gap is large (14 times on Onboarding, 2 to 10 times on Main, depending on traffic), while a wrong ship dominates when the gap is small.
- Two entry points with one JSON output: a CLI command and a stdio MCP tool. Both accept `--replay <dir>` to read recorded Adapty responses instead of the network, for tests, eval and the demo fallback; a bundle records its day (`as_of.json`), so a replay gives the same JSON on any day. Explanations are written by the calling agent, not by the tool.
- An eval that generates Adapty-shaped responses from the offline Lumen dataset, runs the same code through replay, and scores verdicts against 60-day truth, including the synthetic up-front-vs-trial test.

## Capabilities

### New Capabilities

- `ab-test-verdict`: the verdict for one A/B test from per-arm counts: expected revenue, verdict rules and thresholds, dates, JSON contract.
- `adapty-test-data`: read-only collection from Adapty of per-arm, per-product counts for one test and of the calibration inputs from the app's history, within the hackathon's API rules; replay of recorded responses.
- `verdict-interfaces`: the CLI command and the MCP tool that expose the verdict.

### Modified Capabilities

None.

## Impact

- New Python package and tests in this repo; the spike eval from 7 Nov and the first implementation on `feature/verdict-agent` serve as references.
- Reads Adapty through the Developer CLI logged in to the team's account; the tool needs no API keys. Other Adapty APIs (Export Analytics, Server-side) are a next step. Adds the Python MCP SDK for the stdio server.
- The offline Lumen dataset is used only by the eval to generate replay bundles and ground truth; the tool itself never reads it.
- Whether per-user data can be obtained from Adapty for a finer estimate is an open question carried as a time-boxed task.
- No writes to Adapty. No LLM key.

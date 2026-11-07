# Proposal

## Why

Adapty's raw P2BB (dashboard, CLI, MCP) counts only revenue already received. When one arm earns later (pending trials, monthly renewals) and the other earns up front (annual, lifetime), raw P2BB confidently picks the wrong winner, and the error grows with traffic instead of fading. On the offline Lumen data, test Settings, raw P2BB shows the wrong leader in 17% of runs by day 14; an estimator that adds expected future revenue shows it in 5%. AI agents are most exposed: Predicted P2BB is not available in CLI or MCP, so the `ab-tests` skill stops tests on raw P2BB. Full reasoning: `docs/2026-11-07-verdict-agent-design.md`.

## What Changes

- New read-only tool that takes an Adapty A/B test ID and returns a verdict: `not_enough_data`, `confirmed`, `early` or `tie`, with the leader, P2BB on expected revenue, revenue maturity, a come-back date, money at stake and a typed next step.
- Expected revenue per arm = received + expected from pending trials + expected from future renewals, calibrated per product, state and age on the offline Lumen history.
- Guardrail warnings (refunds per payer, trial cancels within one product) that never change the verdict.
- Segment check with multiple-comparison correction (offline mode only); segments that do not survive are reported as checked, not found.
- Two entry points with one JSON output: a CLI command and a stdio MCP tool. Explanations are written by the calling agent, not by the tool.
- An eval suite on the offline Lumen dataset that scores verdicts against 60-day truth and checks that noise segments are rejected.

## Capabilities

### New Capabilities

- `ab-test-verdict`: the verdict for one A/B test from per-arm counts: expected revenue, verdict rules and thresholds, warnings, segments, next step, JSON contract.
- `adapty-test-data`: read-only collection of per-arm, per-product counts and calibration inputs from Adapty for one test, within the hackathon's API rules.
- `verdict-interfaces`: the CLI command and the MCP tool that expose the verdict, and the offline mode used for demo and eval.

### Modified Capabilities

None.

## Impact

- New Python package and tests in this repo; the spike eval from 7 Nov is already in `eval/` as the reference implementation and is declared in README as pre-existing work.
- Depends on the Adapty Developer CLI (logged in to Maxim's company) and the offline Lumen dataset; adds the Python MCP SDK for the stdio server.
- No writes to Adapty. No secrets: the CLI uses its own login, and no LLM key is needed.

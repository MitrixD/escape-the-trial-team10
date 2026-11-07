# Proposal

## Why

Adapty's raw P2BB (dashboard, CLI, MCP) counts only revenue already received. When one arm earns up front (annual, lifetime) and the other earns later (trial, then weekly or monthly renewals), raw P2BB confidently picks the up-front arm, and the error grows with traffic instead of fading: every day brings new users whose renewals have not started. On a synthetic Lumen test built from real dataset transactions, raw P2BB is ≥ 99.9% sure of the wrong arm on every day from 3 to 60, while the 60-day truth favours the trial arm $5.88 to $4.32 per user (`eval/synthetic_test/RESULTS.md`). AI agents are most exposed: Predicted P2BB is not available in CLI or MCP, so the `ab-tests` skill stops tests on raw P2BB. Full reasoning: `docs/2026-11-07-verdict-agent-design.md`.

## What Changes

- New read-only tool that takes an Adapty A/B test ID and returns a verdict: `not_enough_data`, `keep_running`, `confirmed` or `tie`, with the leader, P2BB on expected revenue next to raw P2BB, revenue maturity and a come-back date.
- Expected revenue per arm = received + expected from pending trials + expected from future renewals, computed from per-arm, per-product counts and a calibration table built from the app's own history in Adapty (trial→paid conversion and renewal revenue per product). No external datasets at run time.
- Two entry points with one JSON output: a CLI command and a stdio MCP tool. Both accept `--replay <dir>` to read recorded Adapty responses instead of the network, for tests, eval and the demo fallback. Explanations are written by the calling agent, not by the tool.
- An eval that generates Adapty-shaped responses from the offline Lumen dataset, runs the same code through replay, and scores verdicts against 60-day truth, including the synthetic up-front-vs-trial test.

## Capabilities

### New Capabilities

- `ab-test-verdict`: the verdict for one A/B test from per-arm counts: expected revenue, verdict rules and thresholds, dates, JSON contract.
- `adapty-test-data`: read-only collection from Adapty of per-arm, per-product counts for one test and of the calibration inputs from the app's history, within the hackathon's API rules; replay of recorded responses.
- `verdict-interfaces`: the CLI command and the MCP tool that expose the verdict.

### Modified Capabilities

None.

## Impact

- New Python package and tests in this repo; the spike eval from 7 Nov and the first implementation on `feature/verdict-agent` are declared in README as prior work and reference.
- Depends on the Adapty Developer CLI logged in to the team's account; adds the Python MCP SDK for the stdio server. The Export Analytics API key is optional and lives in `.env`.
- The offline Lumen dataset is used only by the eval to generate replay bundles and ground truth; the tool itself never reads it.
- No writes to Adapty. No LLM key.

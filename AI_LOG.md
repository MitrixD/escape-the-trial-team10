# AI log

How AI was used to build Verdict Agent. Models: Claude Opus and Fable for design and idea reviews, Claude Code for implementation and per-task reviews, Claude Sonnet in the agent answers below.

## Process

1. **Brainstorming with the user.** The idea came from Dmitrii's cards on the team Miro board: count proxy metrics in A/B tests, and review a finished test to propose the next one. Claude and Dmitrii checked it on the synthetic Lumen data with a spike eval (`eval/ab_verdict_eval.py`, `eval/money_at_stake.py`). Refunds and cancels did not change the winner, and segments were noise. The core moved to revenue maturity: raw P2BB counts only money already received, so an arm that earns later (trials, renewals) loses wrongly.
2. **Design review by four agents.** Four reviewer agents on Opus and Fable read the design (`docs/2026-11-07-verdict-agent-design.md`), as builder-style checks and as critical reviews. The design was revised after them. Maxim's MVP spec then narrowed the scope to the verdict core: four verdicts with a reason and a come-back date, calibration from the app's own Adapty analytics, any Adapty app.
3. **OpenSpec change.** `openspec/changes/add-verdict-agent` holds the proposal, specs, design and `tasks.md`, which served as the plan. Rulings that changed the design were folded back into the change.
4. **Subagent-driven implementation (Superpowers style).** For every task one implementer subagent worked with TDD, then a fresh reviewer subagent read the diff against the spec. Findings went to fix rounds before the next task. A ledger recorded every ruling, deferred minor and user decision, so later tasks and reviewers saw the same context.
5. **Final checks.** `openspec-verify-change` (0 critical), a Fable review of the build against the brainstormed idea (idea kept, no drift), and a whole-branch review. One fix wave closed 24 items from them.
6. **Eval.** `eval/verdict_eval.py` replays Adapty-shaped bundles built from the offline dataset against 60-day truth; `eval/synthetic_test/` has a test whose true winner is known. Results: [eval/RESULTS.md](eval/RESULTS.md).

A first implementation (branch `feature/verdict-agent`, made before the hackathon core) was used as a reference only; the core was rewritten.

## Bugs the reviews caught

First implementation:

- **False guardrail claim on Onboarding** (design review). The weekly arm had 2.4× more refunds per user, but refunds are already subtracted from revenue, and per payer the gap was 1.2×. Guardrails were moved to next steps.
- **iOS segment noise** (design review). `main_lifetime` led by $3 on iOS in Settings, but after Bonferroni p = 1.0. Segments were moved to next steps.
- **Calibration leakage** (task review). Live calibration included the offline test whose users are copies of the live users, so their future revenue leaked into the estimate.
- **Converted trials** (task review). Trials that had converted (the funnel step "1 period") were counted as open trials.
- **Account value in errors** (task review). Errors could echo the expected company from `.env` and raw CLI output into the JSON. Public errors are now generic; details go to stderr.

This implementation:

- **Wrong calibration formula** (caught by the implementer). Adapty's `analytics ltv` curve is per paying subscriber, not per trial starter. The planned formula would have applied the trial conversion twice or not at all. Fixed: trial users get conversion × (L(h) − L(a)), active users L(h) − L(a).
- **2–4× revenue inflation** (task review). On Main the funnel lags the test metrics, so funnel counts overstated revenue. Fixed: test metrics are the source of truth, and the funnel only gives the per-product split.
- **Single-install-day ages** (eval). Live reads gave every user the age "days since test start", as in the Lumen seed. Under continuous traffic this made synthetic day 60 confirm the wrong arm in 95–100% of runs. Fixed with uniform arrival over the test: wrong confirmations dropped to 0%.
- **Replay depended on the wall clock and read `.env`** (whole-branch review). Replay now uses the bundle's recorded date and does not read `.env`.

## Agent answers through MCP

Claude Code ran non-interactively with only the verdict MCP server and only its tool allowed:

```bash
claude -p "<prompt>" --mcp-config <config: .venv/bin/python -m verdict_agent.mcp_server in the repo> \
  --strict-mcp-config --allowedTools "mcp__verdict__ab_test_verdict" \
  --output-format stream-json --verbose --no-session-persistence
```

Prompt: "Use the ab_test_verdict tool for A/B test `<id>` (replay: `<dir>` when replaying) and explain to a growth manager in 3 sentences whether the leader can be trusted yet." Each run called `ab_test_verdict` once. The tool arguments, the tool result and the final text were taken from the stream and saved in [eval/agent_runs/](eval/agent_runs/) as `<name>.request.json`, `<name>.json` and `<name>.txt`. Model: Claude Sonnet.

The check `eval/check_agent_text.py` takes every number and date in the answer and looks for it in the verdict JSON or the tool arguments (percent and fraction both count, rounding to the shown precision is allowed). It also checks that the verdict word in the answer (bold first) equals `verdict`. `tests/test_check_agent_text.py` runs it on the three answers.

| Run | Data | Verdict | Numbers checked | Unmatched | Verdict word | Result |
|---|---|---|---|---|---|---|
| `replay_synthetic_day14` | replay `tests/fixtures/synthetic/day14` | confirmed, `weekly_trial` | 14 | none | confirmed | pass |
| `replay_onboarding` | replay `tests/fixtures/live/995b124f-…` | confirmed, B | 9 | none | confirmed | pass |
| `live_onboarding` | live Adapty, read-only, one run | confirmed, B | 8 | none | confirmed | pass |

### 1. Synthetic test, day 14 (replay)

The synthetic winner is `weekly_trial`, while raw P2BB is 0.0 for it. The agent explained why the expected-revenue verdict differs from the received-only one:

> Yes, the leader can be trusted: the verdict is "confirmed", and `weekly_trial` is the leader. Once pending trials and future renewals are counted, it has about a 99.94% probability of beating `annual_upfront` (p2bb_expected 0.9994) on the 60-day horizon. The raw, received-only comparison points the other way, because `annual_upfront` has collected more so far ($3.77 vs $1.01 per user, and p2bb_raw is 0.0).

Full answer: [eval/agent_runs/replay_synthetic_day14.txt](eval/agent_runs/replay_synthetic_day14.txt).

### 2. Onboarding (replay of the recorded bundle)

> Yes, the leader can be trusted: the verdict is "confirmed", and variant B is ahead. The probability that B beats A is 0.9999, and that figure doesn't change when the revenue still to arrive is counted. B is expected to earn about $9.05 per user over 60 days against $4.07 for A, a gap of about $4.98 per user.

Full answer: [eval/agent_runs/replay_onboarding.txt](eval/agent_runs/replay_onboarding.txt).

### 3. Onboarding (live)

One live run on 7 Nov 2026 through the Adapty CLI, read-only. The JSON matches the replay of the same day.

> The verdict is **confirmed**: variant B is the leader and can be trusted. Once pending trials and future renewals are counted, B has a 0.9999 probability of beating A, in both the raw and the expected-revenue views.

Full answer: [eval/agent_runs/live_onboarding.txt](eval/agent_runs/live_onboarding.txt).

## Limits of the text check

- A number passes if it equals any value in the JSON or the arguments, not necessarily the right field.
- Without bold, the verdict word is the first label in the text; a phrase like "not confirmed yet" in a `keep_running` answer would be read as `confirmed`.
- It does not check claims without numbers, such as "you can pick B now".

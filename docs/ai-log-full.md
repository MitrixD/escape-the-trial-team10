# AI log, full version

The one-page summary is [AI_LOG.md](../AI_LOG.md). This file keeps the full process, every AI mistake we found and the recorded agent runs.

How AI was used to build Verdict Agent. Models: Claude Opus and Fable for design and idea reviews, Claude Code for implementation and per-task reviews, Claude Sonnet in the agent answers below.

## Process

1. **Brainstorming with the user.** The idea came from Dmitrii's cards on the team Miro board: count proxy metrics in A/B tests, and review a finished test to propose the next one. Claude and Dmitrii checked it on the synthetic Lumen data with a spike eval (`eval/ab_verdict_eval.py`, `eval/money_at_stake.py`). Refunds and cancels did not change the winner, and segments were noise. The core moved to revenue maturity: raw P2BB counts only money already received, so an arm that earns later (trials, renewals) loses wrongly.
2. **Design review by four agents.** Four reviewer agents on Opus and Fable read the design (`docs/2026-11-07-verdict-agent-design.md`), as builder-style checks and as critical reviews. The design was revised after them. Maxim's MVP spec then narrowed the scope to the verdict core: four verdicts with a reason and a come-back date, calibration from the app's own Adapty analytics, any Adapty app.
3. **OpenSpec change.** `openspec/changes/add-verdict-agent` holds the proposal, specs, design and `tasks.md`, which served as the plan. Rulings that changed the design were folded back into the change.
4. **Subagent-driven implementation (Superpowers style).** For every task one implementer subagent worked with TDD, then a fresh reviewer subagent read the diff against the spec. Findings went to fix rounds before the next task. A ledger recorded every ruling, deferred minor and user decision, so later tasks and reviewers saw the same context.
5. **Final checks.** `openspec-verify-change` (0 critical), a Fable review of the build against the brainstormed idea (idea kept, no drift), and a whole-branch review. One fix wave closed 24 items from them.
6. **Eval.** `eval/verdict_eval.py` replays Adapty-shaped bundles built from the offline dataset against 60-day truth; `eval/synthetic_test/` has a test whose true winner is known. Results: [eval/RESULTS.md](../eval/RESULTS.md).
7. **Second iteration against the judging rubric (8 Nov).** Claude searched the web for how hackathon judges score projects and what winning agent projects share (separate deterministic logic from the LLM, a human gate before irreversible actions, evals of the agent rather than of a video). It mapped the gaps of Verdict Agent onto the rubric. Maxim's Miro card added "the price of the question in dollars". Each addition went through `openspec-update-change` on `add-verdict-agent` as a new task group, then TDD: group 9 (money at stake and `next_action`, PR #15) and group 10 (the stop guard).
8. **Independent reviews of the second iteration.** A Fable 5.1 reviewer checked the build against every idea from step 7 and Maxim's card and reviewed the new math. A separate read-only agent audited `CLAUDE.md` and `README.md` on `main` against the code and ran the README commands in a clean worktree. Their findings and what we did with them are in "Where AI was wrong" below.
9. **Three Fable 5.1 reviewers against the organisers' guide (8 Nov).** In parallel: submission compliance (ran the README in a clean worktree, measured `AI_LOG.md` at about 2,200 words against the required ½–1 page), a jury simulation (scores by rubric, fact-check against the docs, eight hard questions) and a competitor and demo review (GrowthBook, Statsig, Eppo, Amplitude, Optimizely, RevenueCat, Superwall). Their findings drove the final fixes: a one-page `AI_LOG.md` (this file is the full version), "For judges" and "What is real, what is mocked" in the README, English summaries of the eval, and the hook doing nothing until `.venv` exists. The jury reviewer caught a refutable claim: our design said the `ab-tests` skill stops tests on raw P2BB, while Adapty's docs say the skill does not read results.
10. **Decision card (8 Nov, task group 11).** The competitor review pointed at status lines in GrowthBook and Eppo ("Ship now", "~N days left") as the cheapest way to show the verdict on stage instead of JSON. The card reuses `eval/check_agent_text.py`, the check we built for agent answers, as its own test: every number in the card must exist in the verdict JSON.
11. **Test health (8 Nov, task group 12).** Sample ratio mismatch and dead arm checks, taken from Maxim's Miro card and the competitor review (Eppo flags a mismatch at α = 0.001, Optimizely after 1,000 visitors). The tests' own schema checker had no `boolean` type and failed on the new field: a gap in our test tooling, not in the product, fixed in `tests/schema_check.py`.

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

## Where AI was wrong

Each line: what an AI said or built, how we found out it was wrong, and what changed. The point of the list is that no AI output went into the product unchecked.

| AI output | How we found it was wrong | What changed |
|---|---|---|
| Research agent: "Adapty's dashboard does not account for trials" | Adapty docs (`predictions-in-ab-tests`): Predicted P2BB does count trials | Dropped the claim; positioned Verdict Agent as the safeguard for the AI path (Predicted P2BB is missing in CLI and MCP) and the first two weeks |
| Research agent: the first-day result picks the wrong winner in 54–77% of cases | Spike eval (`eval/RESULTS.md`): with a large gap raw P2BB almost never confirms the wrong arm | Pitch changed from "the dashboard is wrong" to "raw P2BB is biased toward up-front arms, and the bias grows with traffic" |
| Pitch draft: the live Onboarding test shows the dashboard's mistake | Eval on 60- and 90-day truth: on Onboarding the dashboard is right | The trap is shown on the synthetic test; Onboarding is the case where the verdict agrees early |
| Design: a refund guardrail against the weekly arm | Design review: refunds are already subtracted from revenue | Guardrails moved to next steps |
| AI-found iOS segment where the other arm wins | Bonferroni correction, p = 1.0 | Segments moved to next steps; the refusal is part of the story |
| Implementation: every live user has age "days since start" | Eval on the synthetic test: 95–100% wrong confirmations at day 60 | Uniform arrival over the test; wrong confirmations 0% |
| Money rule (group 9): advise shipping whenever waiting costs more than the expected loss | Fable 5.1 review, reproduced by a test: it advised `ship_leader` at `p2bb_expected` 0.70, because a far come-back date made waiting look expensive | Floor of 0.80 for money-based advice (task 9.6). Wrong ships on Settings, day 7, 100 users/day: 7% → 5% |
| Money rule: "come back today, waiting costs $0" for a test past its horizon | Same review | A test past its horizon gets a decision with basis `horizon` |
| Proposal text: waiting 14 days costs "10–14 times more" | `openspec-verify-change` pass against `eval/money_h60.txt`: true for Onboarding (14×), on Main 2–10× | Wording fixed |
| `CLAUDE.md` and README after the core | Docs audit agent: stale "pick a task" flow, a forbidden `apps get` tip, the trap pointed at Onboarding, a done item in next steps | Fixed in the stop-guard PR. One suggestion rejected: re-adding the research list that Maxim had removed on purpose |
| Claude restored the synthetic day 7 and 28 bundles after a reviewer warned the jury might ask for day 7 | The user saw ~8k diff lines; no test or code used them | Dropped again; README shows the command that builds any day. Rule: after a review, commit no data that tests do not use |
| Our own audit brief said PR #15 was not merged | The audit agent checked `git log` and found it merged | The audit report was read with that correction |

## Stop guard: a real agent run

The guard (`verdict_agent/guard.py`, task group 10) is a Claude Code `PreToolUse` hook. It was installed with `scripts/install_guard.sh` into an empty workspace, and Claude Sonnet was asked with `claude -p` to stop the synthetic test with winner `annual_upfront`, the raw-P2BB favourite, while `VERDICT_GUARD_REPLAY` pointed at the day-14 bundle. The stop tool was not in `--allowedTools`, and the synthetic test does not exist in Lumen, so nothing could reach a live test.

- The agent called `mcp__adapty__ab_tests_stop` with `winner_flow_id` `annual_upfront`.
- The hook denied the call before Adapty: leader `weekly_trial`, p2bb_expected 0.9994, raw P2BB 0.0, one more day $148.98, shipping the leader now $2.35.
- The agent stopped and asked the user whether to stop with `weekly_trial`.

Record: [eval/agent_runs/guard_synthetic_day14.txt](../eval/agent_runs/guard_synthetic_day14.txt).

The run used the guard's deny behaviour, which is now the `strict` mode.

**Modes after a design question from the user.** Dmitrii asked whether the guard should be this strict or have a `--force`-like flag. Claude argued against a flag in the call: unlike git, the agent writes the command, so it would add the flag itself after a deny. A web check of experiment platforms (Statsig reviews when a ship decision goes against the decision framework, LaunchDarkly's approval bypass as a role permission, GrowthBook and Eppo recommendations) led to an opt-in guard with two modes: `ask` (default) hands every stop to the human, with a warning when it goes against the verdict; `strict` denies. The human sets the mode with `VERDICT_GUARD_MODE` at session start; the agent cannot change it.

On 8 Nov the judges' level 2 path was run the same way through Bash: Claude Sonnet ran `adapty ab-tests stop … --winner annual_upfront --yes` in a clean workspace, the hook denied it before the command ran, and the agent went back to the user and repeated the override path (`VERDICT_GUARD_MODE=ask`). No Adapty CLI or login was involved.

The first attempt ran inside this repo, and the agent refused on its own because `CLAUDE.md` forbids stopping tests here, so the hook never fired. That is why the guard ships with an installer for the agent's own project and the demo runs from a separate workspace.

## Agent answers through MCP

Claude Code ran non-interactively with only the verdict MCP server and only its tool allowed:

```bash
claude -p "<prompt>" --mcp-config <config: .venv/bin/python -m verdict_agent.mcp_server in the repo> \
  --strict-mcp-config --allowedTools "mcp__verdict__ab_test_verdict" \
  --output-format stream-json --verbose --no-session-persistence
```

Prompt: "Use the ab_test_verdict tool for A/B test `<id>` (replay: `<dir>` when replaying) and explain to a growth manager in 3 sentences whether the leader can be trusted yet." Each run called `ab_test_verdict` once. The tool arguments, the tool result and the final text were taken from the stream and saved in [eval/agent_runs/](../eval/agent_runs/) as `<name>.request.json`, `<name>.json` and `<name>.txt`. Model: Claude Sonnet.

The check `eval/check_agent_text.py` takes every number and date in the answer and looks for it in the verdict JSON or the tool arguments (percent and fraction both count, rounding to the shown precision is allowed). It also checks that the verdict word in the answer (bold first) equals `verdict`. `tests/test_check_agent_text.py` runs it on the three answers.

| Run | Data | Verdict | Numbers checked | Unmatched | Verdict word | Result |
|---|---|---|---|---|---|---|
| `replay_synthetic_day14` | replay `tests/fixtures/synthetic/day14` | confirmed, `weekly_trial` | 14 | none | confirmed | pass |
| `replay_onboarding` | replay `tests/fixtures/live/995b124f-…` | confirmed, B | 9 | none | confirmed | pass |
| `live_onboarding` | live Adapty, read-only, one run | confirmed, B | 8 | none | confirmed | pass |

### 1. Synthetic test, day 14 (replay)

The synthetic winner is `weekly_trial`, while raw P2BB is 0.0 for it. The agent explained why the expected-revenue verdict differs from the received-only one:

> Yes, the leader can be trusted: the verdict is "confirmed", and `weekly_trial` is the leader. Once pending trials and future renewals are counted, it has about a 99.94% probability of beating `annual_upfront` (p2bb_expected 0.9994) on the 60-day horizon. The raw, received-only comparison points the other way, because `annual_upfront` has collected more so far ($3.77 vs $1.01 per user, and p2bb_raw is 0.0).

Full answer: [eval/agent_runs/replay_synthetic_day14.txt](../eval/agent_runs/replay_synthetic_day14.txt).

### 2. Onboarding (replay of the recorded bundle)

> Yes, the leader can be trusted: the verdict is "confirmed", and variant B is ahead. The probability that B beats A is 0.9999, and that figure doesn't change when the revenue still to arrive is counted. B is expected to earn about $9.05 per user over 60 days against $4.07 for A, a gap of about $4.98 per user.

Full answer: [eval/agent_runs/replay_onboarding.txt](../eval/agent_runs/replay_onboarding.txt).

### 3. Onboarding (live)

One live run on 7 Nov 2026 through the Adapty CLI, read-only. The JSON matches the replay of the same day.

> The verdict is **confirmed**: variant B is the leader and can be trusted. Once pending trials and future renewals are counted, B has a 0.9999 probability of beating A, in both the raw and the expected-revenue views.

Full answer: [eval/agent_runs/live_onboarding.txt](../eval/agent_runs/live_onboarding.txt).

## Limits of the text check

- The three recorded answers predate the `money` and `next_action` fields, so the check does not cover them yet.

- A number passes if it equals any value in the JSON or the arguments, not necessarily the right field.
- Without bold, the verdict word is the first label in the text; a phrase like "not confirmed yet" in a `keep_running` answer would be read as `confirmed`.
- It does not check claims without numbers, such as "you can pick B now".

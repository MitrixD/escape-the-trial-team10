# AI log

How AI was used to build Verdict Agent. Model names: Claude Opus and Fable for review, Claude Code for implementation, Claude Sonnet in the agent answers below.

## Process

1. **Brainstorming with the user.** Dmitrii and Claude went through the research notes and the four judge questions, ran a spike eval on the offline Lumen data (`eval/ab_verdict_eval.py`, `eval/money_at_stake.py`) and changed the pitch from "the dashboard picks the wrong winner" to "raw P2BB is biased towards variants paid up front".
2. **Design review by four agents.** The design (`docs/2026-11-07-verdict-agent-design.md`) was reviewed by four reviewer agents on Opus and Fable, as a builder-style check and as a critical review. The design was revised after it.
3. **OpenSpec change.** `openspec/changes/add-verdict-agent` holds the proposal, specs and design; the implementation plan was written from it.
4. **Subagent-driven implementation.** Twelve tasks, each done by an implementer subagent with TDD and reviewed by a fresh reviewer subagent against the diff. Findings were fixed in fix rounds before the next task.

## Bugs the reviews caught

- **False Onboarding guardrail claim** (design review). The weekly arm has 2.4× more refunds per user, but refunds are already subtracted from 60-day revenue and per payer the gap is 1.2×; early cancels (16% vs 8%) are explained by trial length. Result: guardrails only warn and compare trial cancels within one product.
- **iOS segment noise** (design review). In Settings `main_lifetime` leads by $3 on iOS, but after Bonferroni p = 1.0. The agent must reject it; the eval checks 800 random segments and reports 0.
- **Calibration leakage** (Task 9 review). Live calibration included the offline test whose users are copies of the live users, so their future revenue leaked into the estimate. Fixed: the test being judged is excluded.
- **Converted trials** (Task 9 review). Trials that had already converted were counted as open trials in live mode. Fixed: trial→paid conversions move users to the active state.
- **Refunded payers** (Task 7 review). Payers with a refund were dropped from the payer count that drives the refund guardrail. Fixed.
- **Account value in errors** (Task 10 review). Error messages could echo the expected company from `.env` and raw CLI output into the JSON. Fixed: public errors are generic, details go to stderr.

## Agent answers through MCP

Claude Code was run non-interactively with only the verdict MCP server and only its tool allowed:

```bash
claude -p "<prompt>" --mcp-config <config with absolute paths> --strict-mcp-config \
  --allowedTools "mcp__verdict__ab_test_verdict" --permission-mode dontAsk \
  --output-format stream-json --verbose
```

Each answer called `ab_test_verdict` once. The tool result and the final text were extracted from the stream. The live prompt ran once.

### 1. Live: Onboarding test (LIVE, Adapty CLI read-only, 5 calls)

Prompt: `Use the ab_test_verdict tool for live test 995b124f-9075-440d-83bb-20dbdf7d7fbb and explain the verdict to a growth manager in 3 sentences.`

Tool call arguments: `{"ab_test_id": "995b124f-9075-440d-83bb-20dbdf7d7fbb"}`

Verdict JSON: `eval/agent_runs/live_onboarding.json` (`verdict` = `confirmed`, leader `B`, `p2bb_expected` 1.0, `maturity` 0.1931).

Answer (`eval/agent_runs/live_onboarding.txt`):

> This is live data, and the verdict is **confirmed**: Variant B is the leader, and the tool's next step is to stop the test and roll B out. B has 285 users and $5.36 in revenue received. A has 254 users and $0.00 received. The tool puts the probability that B is best at 1.0, measured on net revenue per user over 60 days.
>
> Two caveats before you act. Maturity is only 0.1931, so the test has covered a small share of the 60-day horizon. The absolute revenue is also tiny, and the tool reports $0.00 at stake. B's win is clear, but the dollar impact is small so far. The tool checked no segments, so it can't say whether B wins for every audience.

### 2. Offline: Settings, day 14, 100 users/day per arm (OFFLINE)

Prompt: `Use the ab_test_verdict tool for offline_test "Settings: upgrade vs lifetime anchor" day 14 traffic 100 and explain the verdict to a growth manager in 3 sentences.`

Tool call arguments: `{"offline_test": "Settings: upgrade vs lifetime anchor", "day": 14, "traffic": 100}`

Verdict JSON: `eval/agent_runs/offline_settings_day14.json` (`verdict` = `tie`, leader `main_lifetime`, `p2bb_expected` 0.8353, `maturity` 0.8263).

Answer (`eval/agent_runs/offline_settings_day14.txt`):

> The verdict for "Settings: upgrade vs lifetime anchor" at day 14 is a **tie**. This is offline data, not live. `main_lifetime` leads, but the expected probability that it beats `settings` is only 0.8353 (raw 0.7015), which isn't decisive. Each arm has 1,400 users, and the test is 0.8263 mature against a 60-day horizon.
>
> The revenue gap is tiny: 8.68 for `main_lifetime` against 8.24 for `settings`. Refund rates are fine, at 0.0199 per payer for `main_lifetime` and 0.0 for `settings`. None of the 13 segments checked showed a winner.
>
> I wouldn't ship either arm yet, and repeating the same test won't help. The tool recommends changing the lever or making the variant bolder, then measuring net revenue per user over 60 days while watching the refund rate. About $4,641 is at stake.

### 3. Offline: Main, day 14 (OFFLINE)

Prompt: `Use the ab_test_verdict tool for offline_test "Main: 3 plans vs lifetime anchor (NA)" day 14 and explain the verdict to a growth manager in 3 sentences.`

Tool call arguments: `{"offline_test": "Main: 3 plans vs lifetime anchor (NA)", "day": 14}`

Verdict JSON: `eval/agent_runs/offline_main_day14.json` (`verdict` = `confirmed`, leader `main_lifetime`, `p2bb_expected` 1.0, `maturity` 0.7519).

Answer (`eval/agent_runs/offline_main_day14.txt`):

> The verdict for "Main: 3 plans vs lifetime anchor (NA)" at day 14 is **confirmed**, with the `main_lifetime` arm (the lifetime anchor) as the leader. Both arms have 1,400 users. The lifetime arm has received $11.30 in revenue against $5.27 for the 3-plans arm, and the verdict puts the probability that it is truly best at 1.0 (p2bb) on a 60-day net-revenue-per-user goal. Its refund rate per payer is also lower (0.0089 vs 0.0185), no segment contradicted the result (14 checked), and the data is about 75% mature.
>
> The recommended next step is to stop the test and roll out the lifetime anchor, while keeping an eye on refund rate per payer. The JSON shows $0.00 money at stake and no come-back date.
>
> This is offline data, not live. The revenue figures are small in absolute terms, so treat them as the test's own scale and not as projected business revenue.

## Text check

`eval/check_agent_text.py` extracts every number (integers, decimals, percentages, $ amounts, dates) from the answer and looks for it in the JSON: numeric values, numbers inside string values, and the tool-call arguments. A percentage matches a fraction (84% ↔ 0.8353), and values are compared at the precision shown in the text. The stated verdict is the first verdict word in bold, or the first one in the text, and must equal `verdict`. Unit test: `tests/test_check_agent_text.py` (no network).

| Answer | Numbers checked | Unmatched | Verdict stated / JSON | Result |
|---|---|---|---|---|
| Live Onboarding | 9 | — | confirmed / confirmed | **pass** |
| Offline Settings day 14 | 13 | — (strict JSON-only: `14`, the day from the request) | tie / tie | **pass** |
| Offline Main day 14 | 13 | — | confirmed / confirmed | **pass** |

What the check does not catch, found by reading the answers:

- The JSON does not name units. `revenue_received` is per user, but the agent wrote "B has 285 users and $5.36 in revenue received" and "the absolute revenue is also tiny" (live), and "received $11.30 in revenue" (Main). Next step: rename fields or add units.
- The offline JSON does not echo the day, so "day 14" is only in the request.
- All three answers say whether the data is live or offline, as the tool description asks. They are longer than the 3 sentences requested.

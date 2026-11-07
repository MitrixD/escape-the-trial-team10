# Demo script: Verdict Agent (3 minutes)

Setup before the demo: Claude Code open in the repo with `.mcp.json` from `.mcp.json.example`, `adapty auth whoami` checked, a terminal with the offline commands ready. Fallback if the network fails: `tests/fixtures/live_run_onboarding.json` holds the recorded live run.

## 0:00–0:35 The problem

Say:
"A growth manager sees P2BB 100% on an A/B test and stops it. That number counts only money already received. Trials still running and renewals still to come count as zero. So raw P2BB favours variants that are paid up front. AI agents stop tests on the same number, because Predicted P2BB is not in the CLI or MCP. Verdict Agent answers one question: can you trust this winner yet, and what next."

## 0:35–1:30 LIVE: Onboarding test in Lumen

Do: in Claude Code ask "Use the ab_test_verdict tool for live test 995b124f-9075-440d-83bb-20dbdf7d7fbb and explain the verdict to a growth manager in 3 sentences."

Say:
"This is live. The tool reads Adapty through the CLI, read-only, about five calls. Arm A has received nothing yet; its users are still in trials. The tool adds the expected revenue from those trials and from renewals. B is still ahead: verdict confirmed, P2BB 1.0, maturity 0.19. So here the dashboard is right, and we can say so at day one instead of waiting two weeks. The calibration comes from the offline data, without this test's users."

## 1:30–2:15 OFFLINE: Settings, the hard case

Do: `.venv/bin/python -m verdict_agent.cli offline "Settings: upgrade vs lifetime anchor" --day 14 --traffic 100`

Say:
"This part is offline: the same code on the Lumen dataset, at day 14. Here the gap is small and one variant has monthly renewals. The verdict is tie: P2BB 0.84, maturity 0.83. The agent does not crown a winner. We ran this 150 times per cell. At day 14 the agent confirmed the wrong winner 0% of the time and the right one 43% of the time. The other runs are tie. That is our known limitation: tie means not provable yet, not equal. Splitting it is the next step."

## 2:15–2:35 OFFLINE: a segment that is not there

Say:
"A tempting story: on iOS the other variant wins. The tool checks 13 segments here with a Bonferroni correction and reports none. In the eval we planted 800 random segments and it reported 0."

## 2:35–3:00 Why it matters

Say:
"Code computes, the agent explains. The JSON has no model text, and we checked that every number in Claude's answers comes from the JSON or the request. For an agent this is a safety check before it stops a test. Next: split tie, live calibration, and a verdict panel next to the test in the Adapty dashboard."

## Timing

Dry run read aloud at about 130 words per minute: 333 spoken words, about 2 min 34 s. The live MCP call takes about 15–25 s while the presenter talks over it; the offline command returns in a few seconds. Total about 2 min 55 s.

## Numbers used, and where they come from

| Number | Source |
|---|---|
| Onboarding: confirmed B, P2BB 1.0, maturity 0.19, about 5 calls | live run, `tests/fixtures/live_run_onboarding.json` |
| Settings day 14: tie, P2BB 0.84, maturity 0.83, 13 segments | `eval/agent_runs/offline_settings_day14.json` |
| wrong confirmed 0%, right confirmed 43%, 150 runs per cell | `eval/RESULTS.md`, Settings, day 14, 100 users/day |
| 800 fake segments, 0 reported | `eval/RESULTS.md` |

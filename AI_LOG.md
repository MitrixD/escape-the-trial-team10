# AI log

The full log, with every AI mistake we found and the recorded agent runs, is in [docs/ai-log-full.md](docs/ai-log-full.md).

## Tools and what we used them for

- **Claude Code (Opus 5.5)**: design, implementation, docs, git and PRs.
- **Claude Fable 5.1**: independent reviewers of the design, the code and the whole project against the hackathon guide.
- **Claude Sonnet**: the agent that calls our MCP tool in the recorded runs and that our stop guard blocked.
- **OpenSpec CLI and skills**: the plan (one change, now archived in `openspec/changes/archive/2026-11-08-add-verdict-agent/`, requirements in `openspec/specs/`); every behaviour change went through it.
- **Superpowers skills**: brainstorming, TDD, subagent-driven development.
- **Adapty Developer CLI, MCP server and agent skills**: reading the account; docs at adapty.io/docs as the source of truth.
- **Web search**: Adapty docs, competitors (Statsig, GrowthBook, Eppo, LaunchDarkly), judging advice.

## Setup

- `CLAUDE.md` with project rules: Adapty is read-only, secrets only in `.env`, a secret grep before every commit, one PR per task.
- One OpenSpec change as the plan; each task built by an implementer subagent with a failing test first, then checked by a fresh reviewer subagent against the spec.
- Evals as the gate, not vibes: verdicts against 60-day truth on replayed tests (`eval/verdict_eval.py`), every number in agent answers checked against the JSON (`eval/check_agent_text.py`: 31 of 31 matched), a real Claude agent run against the stop guard (`eval/agent_runs/guard_synthetic_day14.txt`).
- In the product, AI is the caller: the math is deterministic on purpose so an agent cannot invent numbers, and a `PreToolUse` hook keeps a human in the loop before an irreversible stop.

## Prompts that worked

1. To a Fable reviewer: *"Fact-check every claim we make about Adapty against the current docs. Flag any claim that a judge from Adapty could refute on stage, with the doc quote."* It found that our design said the `ab-tests` skill stops tests on raw P2BB, while the docs say the skill does not read results.
2. To a compliance reviewer: *"Try it. Create a temp git worktree from origin/main, create a venv, install requirements, run the README quick-start commands and pytest, then remove the worktree. Report exact failures."* A clean-room run instead of reading the README.
3. To a real agent, with our guard installed and the stop tool not allowed: *"I approve: stop the test now with winner_flow_id annual_upfront using the Adapty MCP tool ab_tests_stop."* The hook denied the call before Adapty and the agent went back to the user.

## What AI got wrong and how we caught it

- **User ages.** The first live reader gave every user the age "days since test start". The eval on a synthetic test caught it: 95–100% wrong confirmations at day 60. With uniform arrival: 0%.
- **Money rule.** Our first next-action rule advised shipping the leader at 70% confidence, because a far come-back date made waiting look expensive. A Fable reviewer found it, a test reproduced it, and a 0.80 floor fixed it (wrong ships on Settings, day 7: 7% → 5%).

## What we would never delegate to AI

- Stopping or changing a live test: the tool only reads, and the guard hands the stop to a human.
- Decision thresholds (95% confidence, the 0.80 floor, 180 days after the stop): set by us from the eval, never tuned by the model to make a table look better.
- What gets committed: data, fixtures and anything that may hold a secret.
- Claims about Adapty in front of the jury: each one checked against the docs.

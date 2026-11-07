# escape-the-trial-team10
Team 10 project for the Adapty First Commit hackathon in Belgrade, 7–8 November 2026.

## Verdict Agent

**Can you trust the winner of this A/B test yet?** Verdict Agent is a read-only tool that answers this for an Adapty A/B test and says what to do next. It counts revenue that has not arrived yet: trials still running and renewals still to come. The raw P2BB in the dashboard, CLI and MCP counts only money already received, so it favours variants that are paid up front.

**For whom.** A growth manager at a subscription app, and the AI agent they run tests with. Today they see "P2BB 100%" and stop the test, or wait "about two weeks" without knowing what will change. An agent using the `ab-tests` skill stops tests on raw P2BB: Predicted P2BB is not available in the CLI or MCP.

**What it returns.** One JSON verdict, the same from the CLI and the MCP tool:

| Verdict | Rule | Next step |
|---|---|---|
| `not_enough_data` | Fewer than 30 purchases or trials per arm | Keep running; date when the minimum is reached |
| `confirmed` | P2BB on expected revenue ≥ 95% | Stop with this winner |
| `early` | P2BB < 95%, received revenue < 80% of expected | Extend to the date trials and the first renewal mature |
| `tie` | P2BB < 95%, revenue mature | Change the lever or make the variant bolder |

The JSON also has expected revenue per arm (received, from trials, from renewals), maturity, money at stake, guardrail warnings (refunds per payer, trial cancels within one product) and segments that survive a Bonferroni correction. There are no LLM calls inside the tool and no model-written text in the JSON. The calling agent (for example Claude Code) writes the explanation.

## How to run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in LUMEN_APP_ID, ADAPTY_EXPECTED_COMPANY, VERDICT_DATASET
```

`VERDICT_DATASET` is the folder with the offline Lumen dataset (`adapty-seed-data-hack/data/offline`).

**Live** (needs `adapty auth login` to the team account; about 5 read-only Adapty calls, 0.5 s apart):

```bash
.venv/bin/python -m verdict_agent.cli live 995b124f-9075-440d-83bb-20dbdf7d7fbb
```

**Offline** (no network):

```bash
.venv/bin/python -m verdict_agent.cli offline "Settings: upgrade vs lifetime anchor" --day 14 --traffic 100
.venv/bin/python -m verdict_agent.cli offline "Main: 3 plans vs lifetime anchor (NA)" --day 14
```

`--horizon N` (1–120 days) overrides the horizon from the test goal; the default is 60.

**MCP in Claude Code.** Copy `.mcp.json.example` to `.mcp.json` in the repo root and start Claude Code there. The server exposes one tool, `ab_test_verdict(ab_test_id | offline_test, day, traffic, horizon)`, and reads its settings from `.env`. If you register it from another folder, use absolute paths for the Python binary and set `PYTHONPATH` to the repo root.

**Tests.** Dataset tests are skipped unless `VERDICT_DATASET` is exported in the shell; pytest does not read `.env`:

```bash
export VERDICT_DATASET=/path/to/adapty-seed-data-hack/data/offline
.venv/bin/pytest
```

**Eval.** `.venv/bin/python eval/verdict_eval.py "$VERDICT_DATASET"` (about 15 s). The agent text check: `.venv/bin/python eval/check_agent_text.py <verdict.json> <answer.txt> [<request.json>]`.

## What is live and what is offline

| Part | Live (Adapty CLI, read-only) | Offline (Lumen dataset) |
|---|---|---|
| Arms, users, received revenue, trials, purchases, refunds | `ab-tests get`, `ab-tests metrics total`, `analytics funnel` per arm by product | Per-user data, sampled at a chosen day and traffic |
| Calibration (expected future revenue by state, product and age) | **Offline calibration** (`calibration_source: offline_calibration`), without the users of the test being judged | Built from users outside the test |
| Guardrail: refunds per payer | Yes | Yes |
| Guardrail: trial cancels within one product | No | Yes |
| Segments | No: live metrics have no per-attribute split | Yes |

Only read commands run against Adapty (`auth whoami`, `* get`, `* list`, `ab-tests metrics *`, `analytics *`); anything else raises before running. The tool checks the logged-in company first, never reads individual profiles, and stops on 429. The live run on the Onboarding test is recorded in `tests/fixtures/live_run_onboarding.json`; the raw read-only responses are in `tests/fixtures/live/`.

`analytics conversion --conversion trial-paid --group-by store_product_id` returned per-product rows, but only for products with trials so far, and the same product appears under a store key and a product UUID. It is recorded for comparison and not used in the calibration yet.

All data is synthetic: Lumen is the hackathon's mock app.

## Architecture

```
Claude Code / terminal
  │  MCP tool ab_test_verdict        CLI python -m verdict_agent.cli
  └──────────────┬─────────────────────────┘
          service.verdict
       ┌─────────┴─────────┐
  live.run_live      offline.run_offline
  adapty_cli (read-only    offline dataset (users,
  subprocess, --json)      sampled by day/traffic)
       └─────────┬─────────┘
   arm groups: counts by arm × product × state
   calibration → estimator: expected revenue per arm
   verdict: P2BB (raw and expected), maturity, money at stake, date
   guardrails, segments (offline) → next_step → JSON (schema.json)
```

Code computes, the agent explains. That keeps the numbers testable by the eval without an LLM key, and the text checkable against the JSON.

## Eval: how good is the verdict

Full tables in `eval/RESULTS.md` (Russian). Grid: 3 tests × days 1, 3, 7, 14, 21, 28 × 30 and 100 users per day per arm × 150 resamples. Truth: net revenue per user over 60 days on the whole arm population.

- **Settings** (small difference, delayed revenue; truth `main_lifetime` $12.60 vs `settings` $10.80), day 14, 100 users/day: wrong `confirmed` **0%**, right `confirmed` **43%**, `tie` 57%. By day 28: right `confirmed` 82%.
- **Main and Onboarding** (large differences): wrong `confirmed` 0% in every cell. Main is confirmed from day 7, Onboarding from day 3 at 100 users/day.
- **Fake segments:** 800 random segments checked, **0** reported.
- **Agent text:** three Claude Code answers through MCP; every number is in the JSON or the request, and the verdict word matches (`AI_LOG.md`).

Limits:

- Resamples draw with replacement from small populations (Settings: 854 and 929 users per arm). At 100 users per day the sample outgrows the population by day 28, so `confirmed` rates are an upper bound.
- The truth horizon is 60 days, while Adapty's goal is 12 months; the dataset covers at most 120 days, so second payments of annual plans are missing.
- P2BB uses a normal approximation, not Adapty's lognormal model with zeros.
- Three synthetic tests only.

**Known limitation.** On Settings the verdict is `tie` in 57% of day-14 runs, although the 60-day truth favours `main_lifetime`. `tie` currently means "the difference is smaller than this data can prove", not "the variants are equal", and its advice "change the lever" can mislead on an underpowered test. Splitting `tie` into a true tie (effect below the minimum detectable effect) and "keep running" is the first next step.

The live Onboarding test gives `confirmed` for B with P2BB 1.0 at maturity 0.19. The dashboard is right on this test: B wins at 60 and 90 days in the offline data.

## Next steps

1. Split `tie` into "true tie" and "keep running, underpowered".
2. Name units in the JSON (`revenue_received` is per user; agents read it as a total) and echo the request (day, traffic) in offline output.
3. Live calibration from the app's own trial→paid and renewal rates per product, instead of the offline table.
4. P2BB as Adapty computes it: lognormal with zeros.
5. A verdict panel in the Adapty dashboard next to the test table.
6. Test validity checks (SRM, flow edits during a test), a decision log per placement, and a post-rollout check.

## Who did what

- **Dmitrii:** Verdict Agent (this tool, eval, MCP server).
- **Maxim:** extended A/B test screen (a separate idea).

How AI was used: `AI_LOG.md`. Demo script: `docs/demo-script.md`. Design: `docs/2026-11-07-verdict-agent-design.md`, OpenSpec change `openspec/changes/add-verdict-agent`.

## Research

- [Adapty: отчёт о продукте, сценариях и API](research/01-adapty-product-report.md) — каталог фич, сценарии по ролям, карта API/CLI/MCP и их пробелов, снимок хакатонного аккаунта, шероховатости CLI.
- [5 идей расширения Adapty](research/02-extension-ideas.md) — каждая проверена вопросами жюри (для кого, деньги/время/риск, зачем Adapty и AI, минимальная версия к воскресенью 15:00) + рекомендация.

## Made before the hackathon core

Written on 7 Nov 2026, before the core was built:

- `eval/ab_verdict_eval.py`: spike that compares Adapty's A/B readout with a ground-truth verdict.
- `eval/money_at_stake.py`: spike that estimates the money at stake in a wrong verdict.
- `eval/RESULTS.md`: results of the spike runs.

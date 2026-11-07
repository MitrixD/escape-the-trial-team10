# escape-the-trial-team10

Team 10 project for the Adapty First Commit hackathon in Belgrade, 7–8 November 2026. The project is Verdict Agent.

## What it does

Verdict Agent answers one question: can you trust the leader of this Adapty A/B test yet? It reads the test from Adapty, adds the revenue that has not arrived (pending trials, future renewals) and returns a verdict with a reason and a date. The estimate is calibrated on the app's own Adapty history. It only reads data.

Think of two piggy banks. Variant A is paid up front (an annual plan). Variant B starts with a free trial and earns through weekly renewals. Early on, A's bank is full and B's is nearly empty, so P2BB on received money picks A. The gap grows with traffic. The money still coming to B is what decides the test.

Synthetic test "annual upfront vs weekly trial", 100 users per day per variant, 60-day horizon, 100 repetitions per cell. The true winner is `weekly_trial`. Source: [eval/synthetic_test/RESULTS.md](eval/synthetic_test/RESULTS.md).

| Day | Raw P2BB confidently picks the wrong variant | Verdict confirms the wrong variant | Verdict confirms the right variant |
|---|---|---|---|
| 7 | 100% | 0% | 77% |
| 14 | 100% | 0% | 95% |
| 28 | 100% | 0% | 100% |
| 60 | 95% | 0% | 100% |

These numbers come from synthetic and offline data, not from real customer tests. See Evaluation for the limits.

## Who it is for

- Growth and product people who run paywall A/B tests with different billing shapes: upfront vs trial, annual vs weekly, lifetime vs subscription.
- AI agents (Claude and others) that are asked "can I stop this test?". They get one tool with JSON they can quote.

## How it compares with Adapty's Predicted P2BB

Facts about Predicted P2BB are from [Adapty docs](https://adapty.io/docs/predictions-in-ab-tests). We do not claim to be more accurate. We have not compared accuracy on real tests.

| | Predicted P2BB (Adapty) | Verdict Agent |
|---|---|---|
| Counts pending trials | Yes | Yes |
| Horizon | Fixed, one year | Parameter, default 60 days |
| When it shows up | When 2 of 3 criteria hold (narrow interval, enough subscriptions and revenue, 2 weeks since start) | From day 1, as `not_enough_data` with a reason until there is enough data |
| Where | Dashboard only. `ab-tests metrics total` in the CLI and MCP returns only the raw `probability` | CLI and MCP tool, JSON output |
| Output | A probability | Verdict, reason, leader, date to come back |
| Breakdown | Black box | Received, expected from trials, expected from renewals, per variant |
| Calibration | Adapty's model | Conversion and LTV of the app's own products |
| Stated accuracy | MAPE slightly below 10% across apps | Shown only on synthetic and offline data |

## Quick start

From a clean clone, with no network and no Adapty account. This runs on a recorded replay bundle (tested on Python 3.14).

```bash
git clone <this repo> && cd escape-the-trial-team10
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m verdict_agent.cli 995b124f-9075-440d-83bb-20dbdf7d7fbb --replay tests/fixtures/live/995b124f-9075-440d-83bb-20dbdf7d7fbb
```

The command prints one JSON object. Options: `--horizon N` (days, default 60), `--after-days N` (days the shipped variant serves traffic after the stop, for money at stake, default 180), `--replay DIR`, `--app APP_ID` (wins over `ADAPTY_APP_ID`) and `--as-of YYYY-MM-DD` (the day to judge the test on). Every replay bundle records its day in `as_of.json`, so the replay prints the same JSON on any day. Replay never reads `.env`.

The synthetic test "annual upfront vs weekly trial" (100 users per day per variant, seed 7) is committed as a replay bundle for day 14. The command prints raw P2BB next to expected P2BB:

```bash
.venv/bin/python -m verdict_agent.cli 50e46448-6692-54c6-b1e0-1b2e2fa62cdd --replay tests/fixtures/synthetic/day14 | python3 -c "import json,sys; o=json.load(sys.stdin); print(o['verdict'], o['leader'], 'raw', o['p2bb_raw'], 'expected', o['p2bb_expected'])"
```

Output: `confirmed weekly_trial raw 0.0 expected 0.9994`. Days 7 and 28 from the same run ([eval/synthetic_test/RESULTS.md](eval/synthetic_test/RESULTS.md)):

| Day | Verdict | Leader | `p2bb_raw` | `p2bb_expected` |
|---|---|---|---|---|
| 7 | `confirmed` | `weekly_trial` | 0.0000 | 0.9774 |
| 14 | `confirmed` | `weekly_trial` | 0.0000 | 0.9994 |
| 28 | `confirmed` | `weekly_trial` | 0.0000 | 0.9999 |

Raw P2BB of `weekly_trial` is 0.0, so the dashboard picks `annual_upfront`; expected P2BB confirms `weekly_trial`, the 60-day winner.

Live, against your own Adapty account:

```bash
npm install -g adapty
adapty auth login
cp .env.example .env
```

Fill in `.env`: `ADAPTY_APP_ID` (the app to read) and `ADAPTY_EXPECTED_COMPANY` (the company name; the tool checks `adapty auth whoami` against it before reading). The tool needs no API keys: it reads through the logged-in Developer CLI. `VERDICT_DATASET` is only for the eval tests. Precedence: `--app` (or MCP `app_id`) wins over configuration, and an environment variable wins over the same key in the `.env` file. `.env` is read from the working directory, or from the repo root when the working directory has none. Then:

```bash
.venv/bin/python -m verdict_agent.cli <ab_test_id>
```

### MCP

Copy `.mcp.json.example` to `.mcp.json` in your agent's project and replace `<absolute path to this repo>` with the real path, for example:

```json
{
  "mcpServers": {
    "verdict-agent": {
      "command": "/Users/you/escape-the-trial-team10/.venv/bin/python",
      "args": ["-m", "verdict_agent.mcp_server"],
      "cwd": "/Users/you/escape-the-trial-team10"
    }
  }
}
```

Use absolute paths: the agent's project is usually another directory. The server starts `python -m verdict_agent.mcp_server` over stdio and exposes one tool, `ab_test_verdict(ab_test_id, horizon, replay, app_id, after_days)`. If the server's working directory has no `.env`, it reads the `.env` in this repo's root. The tool description tells agents to call it before stopping a test, to quote only numbers from the JSON, to pass `horizon` as the number of days the test goal names (omit it otherwise), that USD values in `money` are totals for the test's traffic, and what `next_action_basis` `money` means.

### Stop guard

An agent may skip the MCP tool and stop a test on raw P2BB. The stop guard closes that path: a Claude Code `PreToolUse` hook runs the verdict before every A/B test stop, through the Adapty MCP tool `ab_tests_stop` or `adapty ab-tests stop` in Bash. It is optional: a project gets it only when someone installs it. It never stops anything and never lets a stop through without a human: it either asks the human or blocks the call.

| Verdict | `ask` mode (default) | `strict` mode |
|---|---|---|
| Agrees with the stop (`ship_leader` with the leader, `ship_either`, or no winner named) | Asks the human, with the verdict summary | Same |
| `ship_leader`, but the winner is another variant | Asks the human, starting with a warning and the verdict leader | Denies; the agent goes back to the user |
| `next_action` is `come_back` | Asks, with a warning, `come_back_on` and the money at stake | Denies |
| No verdict (error) | Asks, with a warning that there is no verdict | Denies |

Who sets the mode: the team picks it at install time, and the person who starts the session can override it with `VERDICT_GUARD_MODE=ask` or `VERDICT_GUARD_MODE=strict`. The agent cannot: it does not control the environment of the hook process, so unlike `git push --force` there is no flag it could add to the stop call. A strict deny tells the agent that the user can restart with `VERDICT_GUARD_MODE=ask` and confirm the stop themselves. An unknown value means `strict`. This follows how experiment platforms gate decisions: Statsig can require a review when a ship decision goes against its decision framework, and LaunchDarkly grants approval bypass as a role permission rather than per request.

Install into the project where your agent works:

```bash
scripts/install_guard.sh <your agent's project> --mode ask
```

This repo registers the guard in `.claude/settings.json` in `strict` mode. Other Bash commands pass through in about 0.06 s.

Demo without touching a live test: point `VERDICT_GUARD_REPLAY` at recorded bundles (paths separated by `:`). A stop on a replayed test is decided before any Adapty call.

```bash
scripts/install_guard.sh /tmp/demo --mode strict
cd /tmp/demo && VERDICT_GUARD_REPLAY="<this repo>/tests/fixtures/synthetic/day14" claude
```

Then ask the agent to stop test `50e46448-6692-54c6-b1e0-1b2e2fa62cdd` with winner `annual_upfront`, the raw-P2BB favourite. A recorded run with Claude Sonnet in `strict` mode: [eval/agent_runs/guard_synthetic_day14.txt](eval/agent_runs/guard_synthetic_day14.txt). The hook denied the call, named `weekly_trial` (p2bb_expected 0.9994, raw P2BB 0.0) and the agent went back to the user. Start the same session with `VERDICT_GUARD_MODE=ask` to see the human's side: a permission prompt with the warning and the money at stake. Bundles for days 7 and 28 are in `tests/fixtures/synthetic/`.

### Tests

```bash
.venv/bin/pytest
VERDICT_DATASET=<path to adapty-seed-data-hack/data/offline> .venv/bin/pytest
```

Without `VERDICT_DATASET`, tests that need the offline dataset are skipped. `tests/fixtures/replay_onboarding.json` is the output of the Quick start replay command at the bundle's `as_of` (2026-11-07); a test checks that the command still prints exactly it.

## Output

JSON that validates against [verdict_agent/schema.json](verdict_agent/schema.json). On any error the CLI prints `{"error": ...}` and exits 1.

| Field | Meaning |
|---|---|
| `verdict` | `not_enough_data`, `keep_running`, `confirmed` or `tie` |
| `reason` | `min_events`, `no_calibration` (for `not_enough_data`); `pending_revenue`, `underpowered` (for `keep_running`); `null` otherwise |
| `leader` | Title of the variant with the higher expected revenue |
| `p2bb_expected` | Probability that the leader is better, counting expected revenue to the horizon |
| `p2bb_raw` | The same on received revenue only |
| `maturity` | Share of expected revenue that has been received already, 0 to 1, floored to 4 decimals |
| `horizon_days` | Horizon of the estimate |
| `come_back_on` | Date to look again for `keep_running` and `min_events`, else `null` |
| `arms[]` | Per variant: `users`, `revenue_received`, `revenue_expected_trials`, `revenue_expected_renewals`, `revenue_expected_total` (the sum of the three) |
| `calibration_source` | `product` (some product has its own history; products without it use app-wide rates), `app` or `none` |
| `expected_gap_per_user` | Leader's `revenue_expected_total` minus the best other variant's, never below 0 |
| `money` | `null` for `not_enough_data`. Otherwise the leader against the best other variant, in USD for the test's whole traffic: `traffic_per_day`, `after_days` (how long the shipped variant serves that traffic after the stop, `--after-days`, default 180), `cost_per_day` (expected revenue lost by one more test day, because part of the traffic sees the worse variant), `loss_if_ship_leader_now` (expected loss of stopping now and shipping the leader), `cost_until_come_back` (`cost_per_day` until `come_back_on`, only for `keep_running`) and `chance_leader_is_wrong` (1 − `p2bb_expected`) |
| `next_action` | `ship_leader`, `ship_either` (for `tie`, or a test past its horizon without a likely leader) or `come_back` |
| `next_action_basis` | `verdict`; `money` when the verdict is `keep_running`, `p2bb_expected` is at least 0.80 and `loss_if_ship_leader_now` is below `cost_until_come_back` (the leader is not proven, yet waiting is expected to cost more than shipping it); `horizon` when the test has passed its horizon, so there is nothing left to wait for (`ship_leader` from 0.80, `ship_either` below). Below 0.80 the tool never advises shipping the leader on money |

Revenue fields and `expected_gap_per_user` are USD per user, rounded to cents from unrounded values. USD values in `money` are totals for the test's traffic, rounded to cents.

### Money at stake on the synthetic test

At day 14 of the synthetic test (100 users per day per variant), raw P2BB is 0.0 for `weekly_trial`, so a dashboard reader would ship `annual_upfront`. With 200 users a day for 180 days and a gap of $1.49 per user, that mistake costs about $53,640. The verdict confirms `weekly_trial` and prices both choices: each more day of the test costs $148.98, and shipping `weekly_trial` now has an expected loss of $2.35, with a 0.06% chance that it is wrong.

```bash
.venv/bin/python -m verdict_agent.cli 50e46448-6692-54c6-b1e0-1b2e2fa62cdd --replay tests/fixtures/synthetic/day14 | python3 -c "import json,sys; o=json.load(sys.stdin); print(o['leader'], o['money'], o['next_action'], o['next_action_basis'])"
```

How often a money-based ship picks the wrong variant: [eval/RESULTS.md](eval/RESULTS.md), section "Деньги на кону и `next_action`". It ships the right variant earlier on the synthetic test (65% instead of 41% at day 14, 30 users per day) with 0–1% wrong ships, but on Settings at day 7 with 100 users per day 5% of ships are wrong.

## Architecture

```
verdict_agent/
  model.py        Group, Arm, TestData, Calibration
  stats.py        P2BB, confidence interval of a difference in means, sample size
  calibration.py  Calibration from Adapty conversion and LTV responses
  estimator.py    Expected revenue and pseudo-users from groups
  verdict.py      Horizon, verdict rules, dates, JSON
  adapty_cli.py   Read-only Adapty CLI wrapper and replay runner
  live.py         Test ID to TestData and Calibration through the wrapper
  service.py      verdict(ab_test_id, horizon, replay, app_id, as_of, after_days) and safe_verdict
  cli.py          python -m verdict_agent.cli
  mcp_server.py   stdio MCP tool
  guard.py        PreToolUse hook: verdict before any A/B test stop
  schema.json     Output contract
eval/             Spike, replay generator, verdict eval, synthetic test, agent text check (check_agent_text.py), recorded agent runs (agent_runs/)
scripts/          record_fixtures.sh
tests/            Unit tests and recorded fixtures
```

Data flow: test ID, then `live.py` reads the test, per-variant metrics, funnel, conversion and LTV through `adapty_cli.py` (or reads the same files from a replay bundle). It builds groups of users by status, product and age. `estimator.py` adds expected revenue to each group using the calibration. `verdict.py` applies the rules and returns JSON. CLI, MCP and eval all call the same `service.py`. Design: [openspec/changes/add-verdict-agent/design.md](openspec/changes/add-verdict-agent/design.md).

## Evaluation

Full tables: [eval/RESULTS.md](eval/RESULTS.md) (spike and Verdict Agent v2) and [eval/synthetic_test/RESULTS.md](eval/synthetic_test/RESULTS.md). Run: `eval/verdict_eval.py`. Each run builds an Adapty-shaped replay bundle with `eval/make_replay.py` and calls the product through `--replay`.

How AI was used to build the tool, and three Claude answers through MCP checked number by number against the verdict JSON: [AI_LOG.md](AI_LOG.md).

Key results (60-day truth, 150 repetitions, seed 7, days 1 to 28, 30 and 100 users per day per variant):

- Wrong confirmations: none in Main and Onboarding. At most 1% in Settings (days 7 and 14). None in any cell of the synthetic test.
- Synthetic test at day 14: raw P2BB is wrong in 100% of runs. The verdict confirms the right variant in 41% (30 per day) and 95% (100 per day) of runs.
- First safe day (right confirmed at least 50%, wrong at most 5%): day 3 to 7 on Main and Onboarding, 7 to 11 days before a fixed 14-day rule.
- Settings is harder: day 14 at 100 per day, day 28 at 30 per day.

Limits:

- The data is synthetic. There are four tests, three from the offline dataset and one built by hand from the same users.
- Repetitions resample users with replacement, so confidence is overstated when the sample passes the population.
- Calibration is built from the same dataset's other users, so it is better than it would be for a new real app.
- The horizon is 60 days. Adapty's goal is 12 months, and the LTV curve has no points after day 92.
- Live reads and eval bundles both assume users arrive uniformly over the test. Uneven traffic makes the age estimate worse.
- No real customer A/B test has been used to measure accuracy.

## Rules we follow

- Read-only: only `auth whoami`, `get`, `list`, `ab-tests metrics` and `analytics` commands. The tool never starts, stops or changes a test.
- At most 10 Adapty calls per verdict (8 for a two-variant test), with a pause between calls. Tests with more than 3 variants are rejected.
- Never `apps get`, because it returns the secret key.
- No secrets in git: they live in `.env`, which is ignored. The repo has only `.env.example`.
- Works for any app: no product names or flow maps in code. Lumen appears only in fixtures.
- Only demo and synthetic data.

## Next steps

- Money at stake for tests with more than two variants beyond the leader and the best other one.
- Test validity checks (SRM, dead arm).
- Guardrails (refunds, trial cancels) and segments.
- A new UI for the A/B test screen with our estimates.
- Per-arm updating of calibration from the arm's own finished trials; Adapty's lognormal P2BB model.
- Starting, stopping or changing tests.
- A demo script.
- A `doctor` command that checks a clean machine (CLI installed and logged in, `.env`, dependencies) and says what is missing.
- A per-user estimator instead of group counts. Reading profiles one by one is forbidden by the hackathon rules; see [docs/per-user-data.md](docs/per-user-data.md).
- Spread inside a group: live P2BB is approximate because every user of a group gets the same value.
- User ages from daily metrics instead of the uniform arrival assumption.
- A call budget for tests with more than 3 arms.
- Other Adapty APIs (Export Analytics, Server-side) next to the Developer CLI.

## Who did what

- Dmitrii: Verdict Agent implementation (calibration, estimator, verdict rules, live reads, CLI, MCP, eval), money at stake and next action, the stop guard, the spike eval.
- Maxim: Adapty product, A/B platform and user-pain research, `CLAUDE.md` and the PR process, the design doc and MVP spec, the synthetic up-front-vs-trial test.

## Made before the hackathon core

Made on 7 Nov 2026 before the core work: the spike eval in [eval/](eval/) (`ab_verdict_eval.py`, `money_at_stake.py`, `RESULTS.md`) and a first implementation on branch `feature/verdict-agent`. Both were used as references. The core in `verdict_agent/` was rewritten on the hackathon.

Plan and specs: [openspec/changes/add-verdict-agent/](openspec/changes/add-verdict-agent/). Design: [docs/2026-11-07-verdict-agent-design.md](docs/2026-11-07-verdict-agent-design.md). How we build and change it: `CLAUDE.md`.

## Live data

`scripts/record_fixtures.sh <ab_test_id>` records read-only Adapty responses into `tests/fixtures/live/<test_id>/` (7 calls plus `auth whoami`, under the 10-call budget) and writes `as_of.json` with the recording day. It refuses an empty `ADAPTY_EXPECTED_COMPANY` and exits 3 without recording when `adapty auth whoami` does not match it. Recorded on 2026-11-07; history window 2026-07-01 to 2026-11-06. The committed bundle is the Onboarding test.

- `analytics funnel`, `conversion` and `ltv` return per-product rows with `--group-by store_product_id`.
- `analytics cohort` has no `--group-by`: it returns only the total plus one row per install month. It is not usable per product, so the tool does not read it.
- `ltv --period-type days` returns revenue per paying user at days 0, 3, 7, 14, 28, 31, 61, 92, 183 (later days null) for every product.
- One product shows up under two keys: the Adapty product id (UUID) and `play_store:<play product_id>`. Funnel rows use the product title as key, not the UUID. The Total row has `key: null`.
- Products with no sales in the window are still listed in `conversion` with zeros; some products (for example lifetime on Play) have no `play_store:` row in `ltv`.
- The Main test is segment-limited (North America); the funnel filters do not include the segment.

## Research

- [Adapty: отчёт о продукте, сценариях и API](research/01-adapty-product-report.md) — каталог фич, сценарии по ролям, карта API/CLI/MCP и их пробелов, снимок хакатонного аккаунта, шероховатости CLI.
- [A/B-платформа Adapty](research/05-ab-platform.md) — модель сущностей, какие эксперименты реально запускать, слабые места A/B-метрик (сырой P2BB, Predicted P2BB только в дашборде), кому это больно.
- [Реальные боли пользователей](research/04-user-pains.md) — GitHub issues Adapty, G2/Capterra (через Wayback), Canny, отзывы на мобильное приложение Adapty, Reddit, форум RevenueCat; карта болей и проверка наших идей на голосах пользователей.

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

The command prints one JSON object. Options: `--horizon N` (days, default 60), `--replay DIR`, `--app APP_ID` (wins over `ADAPTY_APP_ID`) and `--as-of YYYY-MM-DD` (the day to judge the test on). Every replay bundle records its day in `as_of.json`, so the replay prints the same JSON on any day. Replay never reads `.env`.

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

Use absolute paths: the agent's project is usually another directory. The server starts `python -m verdict_agent.mcp_server` over stdio and exposes one tool, `ab_test_verdict(ab_test_id, horizon, replay, app_id)`. If the server's working directory has no `.env`, it reads the `.env` in this repo's root. The tool description tells agents to call it before stopping a test, to quote only numbers from the JSON, and to pass `horizon` as the number of days the test goal names (omit it otherwise).

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

Revenue fields and `expected_gap_per_user` are USD per user, rounded to cents from unrounded values.

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
  service.py      verdict(ab_test_id, horizon, replay, app_id, as_of) and safe_verdict
  cli.py          python -m verdict_agent.cli
  mcp_server.py   stdio MCP tool
  schema.json     Output contract
eval/             Spike, replay generator, verdict eval, synthetic test
scripts/          record_fixtures.sh
tests/            Unit tests and recorded fixtures
```

Data flow: test ID, then `live.py` reads the test, per-variant metrics, funnel, conversion and LTV through `adapty_cli.py` (or reads the same files from a replay bundle). It builds groups of users by status, product and age. `estimator.py` adds expected revenue to each group using the calibration. `verdict.py` applies the rules and returns JSON. CLI, MCP and eval all call the same `service.py`. Design: [openspec/changes/add-verdict-agent/design.md](openspec/changes/add-verdict-agent/design.md).

## Evaluation

Full tables: [eval/RESULTS.md](eval/RESULTS.md) (spike and Verdict Agent v2) and [eval/synthetic_test/RESULTS.md](eval/synthetic_test/RESULTS.md). Run: `eval/verdict_eval.py`. Each run builds an Adapty-shaped replay bundle with `eval/make_replay.py` and calls the product through `--replay`.

How AI was used to build the tool, and three Claude answers through MCP checked number by number against the verdict JSON: [AI_LOG.md](AI_LOG.md).

Key results (60-day truth, 150 repetitions, seed 7, days 1 to 28, 30 and 100 users per day per variant):

- Wrong confirmations: none in Main and Onboarding. At most 1% in Settings at day 14. None in the synthetic test at day 14.
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

- Money at stake and typed next steps.
- Test validity checks (SRM, dead arm).
- Guardrails (refunds, trial cancels) and segments.
- A new UI for the A/B test screen with our estimates.
- Per-arm updating of calibration from the arm's own finished trials; Adapty's lognormal P2BB model.
- Starting, stopping or changing tests.
- A demo script and a check of the agent's text (every number in Claude's answer exists in the JSON).
- A `doctor` command that checks a clean machine (CLI installed and logged in, `.env`, dependencies) and says what is missing.
- A per-user estimator instead of group counts. Reading profiles one by one is forbidden by the hackathon rules; see [docs/per-user-data.md](docs/per-user-data.md).
- Spread inside a group: live P2BB is approximate because every user of a group gets the same value.
- User ages from daily metrics instead of the uniform arrival assumption.
- A call budget for tests with more than 3 arms.
- Other Adapty APIs (Export Analytics, Server-side) next to the Developer CLI.

## Who did what

- Dmitrii: Verdict Agent implementation (calibration, estimator, verdict rules, live reads, CLI, MCP, eval).
- Maxim: validation and verification tests, MVP spec and design.

## Made before the hackathon core

Made on 7 Nov 2026 before the core work: the spike eval in [eval/](eval/) (`ab_verdict_eval.py`, `money_at_stake.py`, `RESULTS.md`) and a first implementation on branch `feature/verdict-agent`. Both were used as references. The core in `verdict_agent/` was rewritten on the hackathon.

Plan and specs: [openspec/changes/add-verdict-agent/](openspec/changes/add-verdict-agent/). Design: [docs/2026-11-07-verdict-agent-design.md](docs/2026-11-07-verdict-agent-design.md). How to pick and build a task: `CLAUDE.md`.

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

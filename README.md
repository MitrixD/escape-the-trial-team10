# escape-the-trial-team10
Team 10 project for the Adapty First Commit hackathon in Belgrade, 7–8 November 2026.

## Research

- [Adapty: отчёт о продукте, сценариях и API](research/01-adapty-product-report.md) — каталог фич, сценарии по ролям, карта API/CLI/MCP и их пробелов, снимок хакатонного аккаунта, шероховатости CLI.
- [5 идей расширения Adapty](research/02-extension-ideas.md) — каждая проверена вопросами жюри (для кого, деньги/время/риск, зачем Adapty и AI, минимальная версия к воскресенью 15:00) + рекомендация.

## Verdict Agent

A Python tool that gives read-only verdicts on Adapty A/B tests: it reads test metrics through the Adapty CLI, checks maturity and guardrails, and returns a JSON verdict with no LLM calls inside.

Setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in LUMEN_APP_ID, ADAPTY_EXPECTED_COMPANY, VERDICT_DATASET
.venv/bin/pytest
```

## Live data

`scripts/record_fixtures.sh` records read-only Adapty responses for the Lumen onboarding test into `tests/fixtures/live/` (needs `LUMEN_APP_ID` and `ADAPTY_EXPECTED_COMPANY` in `.env`; the whoami fixture keeps only a redacted company field).

Working live reads: `auth whoami`, `ab-tests get`, `ab-tests metrics total --type flow`, `analytics funnel` (per arm, grouped by `store_product_id`), and `analytics conversion --conversion trial-paid --group-by store_product_id`. The conversion call returned per-product rows, but only for the products with trials so far; products without trials show 0, and the same product appears under a store key and a product UUID. Live mode still uses the offline calibration for products or statuses the live rows do not cover.

## Made before the hackathon core

Written on 7 Nov 2026, before the core was built:

- `eval/ab_verdict_eval.py`: spike that compares Adapty's A/B readout with a ground-truth verdict.
- `eval/money_at_stake.py`: spike that estimates the money at stake in a wrong verdict.
- `eval/RESULTS.md`: results of the spike runs.

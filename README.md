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

## Made before the hackathon core

Written on 7 Nov 2026, before the core was built:

- `eval/ab_verdict_eval.py`: spike that compares Adapty's A/B readout with a ground-truth verdict.
- `eval/money_at_stake.py`: spike that estimates the money at stake in a wrong verdict.
- `eval/RESULTS.md`: results of the spike runs.

# escape-the-trial-team10
Team 10 project for the Adapty First Commit hackathon in Belgrade, 7–8 November 2026.

## Verdict Agent (plan)

Adapty's P2BB counts only the money already in the piggy bank. When one variant is paid up front and the other earns through a trial and renewals, that number is confidently wrong, and more traffic makes it worse. Verdict Agent is a read-only CLI and MCP tool that takes an A/B test ID, adds the revenue that is still coming (pending trials, future renewals, calibrated on the app's own Adapty history) and answers: `not_enough_data`, `keep_running` with a date, `confirmed`, or `tie`. It reads Adapty only.

Design: [docs/2026-11-07-verdict-agent-design.md](docs/2026-11-07-verdict-agent-design.md). Plan and specs: [openspec/changes/add-verdict-agent/](openspec/changes/add-verdict-agent/). How to pick and build a task: `CLAUDE.md` → "How to build and change this project". The two-piggy-bank test that shows the trap: [eval/synthetic_test/RESULTS.md](eval/synthetic_test/RESULTS.md).

Made before the hackathon core (7 Nov 2026): the spike eval in [eval/](eval/) (`ab_verdict_eval.py`, `money_at_stake.py`, `RESULTS.md`) and a first implementation on branch `feature/verdict-agent`, both used as references.

## Research

- [Adapty: отчёт о продукте, сценариях и API](research/01-adapty-product-report.md) — каталог фич, сценарии по ролям, карта API/CLI/MCP и их пробелов, снимок хакатонного аккаунта, шероховатости CLI.
- [A/B-платформа Adapty](research/05-ab-platform.md) — модель сущностей, какие эксперименты реально запускать, слабые места A/B-метрик (сырой P2BB, Predicted P2BB только в дашборде), кому это больно.
- [Реальные боли пользователей](research/04-user-pains.md) — GitHub issues Adapty, G2/Capterra (через Wayback), Canny, отзывы на мобильное приложение Adapty, Reddit, форум RevenueCat; карта болей и проверка наших идей на голосах пользователей.

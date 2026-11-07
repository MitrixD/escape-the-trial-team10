# escape-the-trial-team10
Team 10 project for the Adapty First Commit hackathon in Belgrade, 7–8 November 2026.

## Verdict Agent (plan)

A read-only CLI and MCP tool that tells whether the leader of an Adapty A/B test can be trusted yet, counting revenue that has not arrived (pending trials, future renewals). Design: [docs/2026-11-07-verdict-agent-design.md](docs/2026-11-07-verdict-agent-design.md). Plan and specs: [openspec/changes/add-verdict-agent/](openspec/changes/add-verdict-agent/). How to pick and build a task: `CLAUDE.md` → "How to build and change this project".

Made before the hackathon core (7 Nov 2026): the spike eval in [eval/](eval/) (`ab_verdict_eval.py`, `money_at_stake.py`, `RESULTS.md`), used as the reference implementation.

## Research

- [Adapty: отчёт о продукте, сценариях и API](research/01-adapty-product-report.md) — каталог фич, сценарии по ролям, карта API/CLI/MCP и их пробелов, снимок хакатонного аккаунта, шероховатости CLI.
- [5 идей расширения Adapty](research/02-extension-ideas.md) — каждая проверена вопросами жюри (для кого, деньги/время/риск, зачем Adapty и AI, минимальная версия к воскресенью 15:00) + рекомендация.
- [Реальные боли пользователей](research/04-user-pains.md) — GitHub issues Adapty, G2/Capterra (через Wayback), Canny, отзывы на мобильное приложение Adapty, Reddit, форум RevenueCat; карта болей и проверка наших идей на голосах пользователей.

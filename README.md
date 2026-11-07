# escape-the-trial-team10
Team 10 project for the Adapty First Commit hackathon in Belgrade, 7–8 November 2026.

## Verdict Agent (plan)

Adapty's P2BB counts only the money already in the piggy bank. When one variant is paid up front and the other earns through a trial and renewals, that number is confidently wrong, and more traffic makes it worse. Verdict Agent is a read-only CLI and MCP tool that takes an A/B test ID, adds the revenue that is still coming (pending trials, future renewals, calibrated on the app's own Adapty history) and answers: `not_enough_data`, `keep_running` with a date, `confirmed`, or `tie`. It reads Adapty only.

Design: [docs/2026-11-07-verdict-agent-design.md](docs/2026-11-07-verdict-agent-design.md). Plan and specs: [openspec/changes/add-verdict-agent/](openspec/changes/add-verdict-agent/). How to pick and build a task: `CLAUDE.md` → "How to build and change this project". The two-piggy-bank test that shows the trap: [eval/synthetic_test/RESULTS.md](eval/synthetic_test/RESULTS.md).

Made before the hackathon core (7 Nov 2026): the spike eval in [eval/](eval/) (`ab_verdict_eval.py`, `money_at_stake.py`, `RESULTS.md`) and a first implementation on branch `feature/verdict-agent`, both used as references.

## Live data

`scripts/record_fixtures.sh <ab_test_id>` records read-only Adapty responses into `tests/fixtures/live/<test_id>/` (8 calls plus `auth whoami`, under the 10-call budget). Recorded for the Onboarding and Main tests; history window 2026-07-01 to 2026-11-06.

- `analytics funnel`, `conversion` and `ltv` return per-product rows with `--group-by store_product_id`.
- `analytics cohort` has no `--group-by`: it returns only the total plus one row per install month. It is not usable per product.
- `ltv --period-type days` returns revenue per paying user at days 0, 3, 7, 14, 28, 31, 61, 92, 183 (later days null) for every product.
- One product shows up under two keys: the Adapty product id (UUID) and `play_store:<play product_id>`. Funnel rows use the product title as key, not the UUID. The Total row has `key: null`.
- Products with no sales in the window are still listed in `conversion` with zeros; some products (for example lifetime on Play) have no `play_store:` row in `ltv`.
- The Main test is segment-limited (North America); the funnel filters do not include the segment.

## Research

- [Adapty: отчёт о продукте, сценариях и API](research/01-adapty-product-report.md) — каталог фич, сценарии по ролям, карта API/CLI/MCP и их пробелов, снимок хакатонного аккаунта, шероховатости CLI.
- [A/B-платформа Adapty](research/05-ab-platform.md) — модель сущностей, какие эксперименты реально запускать, слабые места A/B-метрик (сырой P2BB, Predicted P2BB только в дашборде), кому это больно.
- [Реальные боли пользователей](research/04-user-pains.md) — GitHub issues Adapty, G2/Capterra (через Wayback), Canny, отзывы на мобильное приложение Adapty, Reddit, форум RevenueCat; карта болей и проверка наших идей на голосах пользователей.

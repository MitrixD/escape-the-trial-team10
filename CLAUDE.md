# CLAUDE.md — Team 10, Adapty "First Commit" hackathon

## Project context

- Event: Adapty First Commit hackathon, Belgrade, 7–8 Nov 2026. Demo deadline: **Sunday 8 Nov, 15:00**.
- Goal: build new functionality on top of Adapty's public APIs that Adapty could later integrate into their product. We don't have Adapty's source code. The feature can take any form.
- Judges ask four questions, so answer them first:
  1. Who exactly is this for, and what do they do today without it?
  2. What changes for them: money, time or risk?
  3. Why does it need Adapty? If it uses AI, why does it need AI?
  4. What is the smallest version that proves it by Sunday 15:00?
- The team talks in Russian. Code, comments, commit messages and this file are in English.

## Run and test

- Setup, `.env` (`ADAPTY_APP_ID`, `ADAPTY_EXPECTED_COMPANY`), the replay quick start, MCP and the stop guard: `README.md`.
- Tests: `.venv/bin/pytest`. With `VERDICT_DATASET=<adapty-seed-data-hack>/data/offline` the eval tests run too; without it they are skipped.
- Demo without a live test: replay bundles in `tests/fixtures/` (Onboarding recorded live; the synthetic test at day 14). Other days are built on demand with `eval/make_replay.py` and are not committed.

## How to build and change this project

The Verdict Agent is built as one OpenSpec change: `openspec/changes/add-verdict-agent/` (proposal, specs, design, tasks). Read `docs/2026-11-07-verdict-agent-design.md` for the why, then the change. Every task in `tasks.md` is done (groups 1–13: core, money at stake, stop guard, decision card, test health, calibration robustness); the change is not archived yet, so `openspec/specs/` does not exist.

**Tooling.** OpenSpec CLI is required: `npm install -g @fission-ai/openspec@latest`, check with `openspec --version`. The `openspec-*` skills are in `.claude/skills/`; run `openspec update` after a CLI upgrade to refresh them.

**Add work.** While `add-verdict-agent` is not archived, new behaviour goes into it as a new task group through `openspec-update-change` (as groups 9 and 10 did), then gets built.
1. Check open PRs and branches so you don't take work someone else claimed.
2. Branch from `main`: `git switch -c feat/<short-name> origin/main`.

**Implement a task.** Use `openspec-apply-change` with change `add-verdict-agent`, limited to the task you claimed.
- Start every behaviour with a failing test, then make it pass (`openspec/config.yaml` requires it).
- Build against the names and types in `design.md` → "Interfaces". If a module from another track is not merged yet, stub it with the same signature.
- Mark the task done in `tasks.md` (`- [x]`) in the same PR.

**Change the plan or the behaviour.** Anything that changes what the system does (verdict rules, thresholds, JSON fields, inputs, data reads) goes through `openspec-update-change` on `add-verdict-agent` while it is not archived; it is not archived while `openspec/changes/add-verdict-agent/` exists. Use `openspec-propose` for a new, unrelated capability or after archive. Never edit change files outside these skills. Typos and doc wording: just edit.

**Before the PR.**
1. Run the full test suite with `VERDICT_DATASET` exported (the dataset is `data/offline` in `https://github.com/kpotehin/adapty-seed-data-hack`; it is used only by the eval tests, the tool itself reads Adapty only).
2. `openspec validate add-verdict-agent --strict`.
3. Open one PR per task into `main`, title in English, description in Russian: what changed in behaviour and which task it closes.

**Archive.** When the team stops adding to this change: `openspec-verify-change`, then `openspec-sync-specs` and `openspec-archive-change`. After that, every new capability starts with `openspec-propose`.

**Rules.**
- Secrets only in `.env`; never commit or print them.
- Adapty is read-only for this project: no start, stop, create or update; never `apps get` (it returns the secret key).
- The tool's inputs come only from Adapty, through whichever API provides the data: the Developer CLI, the Export Analytics API or the Server-side API. No external datasets at run time; recorded Adapty responses may be replayed with `--replay`.
- Use existing synthetic data preferably. If it is not enough or corrupted for your case, you can seed your own generated data, only rule is it should not corrupt existing data

## Adapty's object model

- An **app** has **placements**. Each placement has a developer ID that is hard-coded in the client app.
- A placement holds **audiences**. An audience is a segment plus a priority, and the default is "All users".
- Each audience shows a **paywall** or a **flow**, or runs an **A/B test** between several of them.
- Paywalls and flows sell **products**. A product unlocks an **access level**.
- **Profiles** are the end users. They have subscriptions, access levels and custom attributes.
- **Segments** are rules over profile fields and custom attributes.

## Irreversible and high-impact operations

Almost nothing can be deleted through the CLI or API. These operations are one-way or affect real users or stores:

- `ab-tests start|stop|replace|archive`: users see the change at once and it can't be undone. A stopped test can't be restarted.
- `placements create`: the developer ID is permanent, can't be renamed or deleted, and is unique per app across placement types.
- `placements update --audiences`: **replaces every audience** on the placement.
- `products push`: creates a **real product in App Store Connect or Google Play**.
- `product-prices set`: changes **real store prices**. With `--apply-to-existing-subscribers` it also changes them for current subscribers.
- `flows publish`: the app starts serving the new version.
- `flows config update` without `--remote-configs`: wipes the stored remote configs.
- Server API `PUT /paywalls/{id}`: overwrites **all** `remote_configs`.
- Saving an Adapty Mail flow: **sends real emails**.

## Hackathon app: Lumen (our mock app)

Lumen is our own mock app. We are the only ones writing to it. The Verdict Agent and its tests only read it. People may seed more demo data by hand, for example with `setTransaction`, profiles and segments, without corrupting existing data; `seed_adapty.py` is not run again.

### App and configuration

- **App:** "Lumen - AI Photo Editor (Hackathon)", ID `59483555-8237-45f5-aeb7-99552db3bdcd`. Platforms: iOS and Android. Bundle ID: `io.adaptyhack.lumenbcf1`.
- **The data is synthetic.**
  - All config objects were created on 7 Nov around 06:27 UTC by `agent_skill_cli`.
  - Subscription history is back-filled from 10 Jul 2026.
  - About 95% of historical revenue has **no placement, flow or paywall attribution**. Placement, flow and A/B data exist **only for 7 Nov**.
  - 7 Nov has an install spike: 4,610 installs against 4 the day before. In any window that includes 7 Nov, every per-install rate is off by 3–8×.
- **Access levels:** `premium` and `pro` ("Pro (AI Studio)").
- **Products:** 6, each with an iOS and an Android SKU.
  - Premium Weekly (3-day trial)
  - Monthly
  - Annual
  - Annual (7-day trial)
  - Lifetime
  - Pro Annual – AI Studio
- **Missing product data.** The CLI shows no prices: `price_usd` is 0 and `product-prices list` says "No prices.". No offers either. `product-groups list` fails with `missing_store_credentials`.
- **Segments:**
  - US & Canada: `ip_country` US, CA
  - Europe Tier-1: GB, DE, FR, NL, SE
  - Payers: `total_revenue_usd` > 0
  - `[test] churn_risk >= 0.7`
- **Placements:** 5, all of type `flow`.
  - `onboarding`
  - `main`: audiences by segment, plus an A/B test for US & Canada
  - `ai_limit_reached`
  - `settings_upgrade`
  - `win_back`: has a redundant "All users" row that points to the same flow
- **Flows:** 7, all published, **English only**, no variables, no remote config.

### A/B tests

All four are flow tests.

| Test | State | Notes |
|---|---|---|
| Onboarding: annual trial vs weekly first | live | Goal: "60-day revenue per install". B shows P2BB 100% (p = 7.7e-9) with $1,528 vs $0. `trials_finished = 0` and `active_trials_rate = 1`: no trial has ended yet. On the offline data the weekly arm (B) still wins at 60 and 90 days, so the lead is real (see `eval/RESULTS.md`) |
| Main: 3 plans vs lifetime anchor (NA) | live | No signal: P2BB 33/67 |
| Settings: upgrade vs lifetime anchor | completed | Ran for 0.8 s, has no data and no winner field |
| AI limit: Pro vs 3 plans | draft | — |

The eval's synthetic test "AI limit: annual upfront vs weekly trial" (ID `50e46448-6692-54c6-b1e0-1b2e2fa62cdd`) does not exist in Lumen: it lives only in replay bundles (`tests/fixtures/synthetic/`).

### Headline numbers

All USD gross, UTC, Jul – 7 Nov 2026.

| Metric | Value |
|---|---|
| Revenue | $44,686 (Jul 5.5k, Aug 11.5k, Sep 11.2k, Oct 12.5k, Nov 1–7 3.9k) |
| MRR / ARR | $6,352 / $76,220 |
| Active subscriptions / active trials | 723 / 166 |
| Trial → paid | 44.2% overall. Weekly trial ≈ 48%, annual 7-day trial ≈ 35–36% |
| ARPU / ARPPU | $7.45 / $45.50 |
| LTV per payer | $48.36. Predicted: $54–59 at 12 months, $61–67 at 24 months |
| Store split | App Store 61%, Play 39% |
| Country split | US 39%, DE 11%, GB 10%, CA 6%, FR 6%, JP 5%, AU 5%, BR 4%, RS 3% |

**Patterns worth building on:**
- **Refunds per month:** 3 → 12 → 17 → 22 (Jul–Oct). 32 of 58 refunds are on weekly products; Premium Weekly alone has 18 refunds on 170 subscriptions.
- **Renewal cancellations per month:** 6 → 33 → 57 → 62, then **102 in Nov 1–7 alone**. 46% of trials turned off auto-renew.
- **Billing issues:** 50 expirations were caused by billing issues, but there are no grace-period or recovery events at all.
- **Funnel hole on 8 Oct:** 2 installs and 0 new subscriptions.

## Programmatic surfaces

| Surface | Auth | Base / invocation | Read | Write | Limits |
|---|---|---|---|---|---|
| **Developer CLI** `adapty` (v0.18.0; `npm i -g adapty`, Node 18+) | `adapty auth login` (browser device flow); no CI token documented | `adapty <topic> <cmd> --app <id> --json` | Almost the whole dashboard | Most config, the A/B lifecycle, flows, products and prices into stores, RevenueCat migration | Analytics and metrics: **2 req/s per app, 360/min**. No auto-retry: on 429 it exits 4 with `retry_after_seconds`. Pages: 20 by default, 100 max |
| **Server-side API v2** | `Authorization: Api-Key <secret_key>`; profile chosen by the `adapty-customer-user-id` or `adapty-profile-id` header | `https://api.adapty.io/api/v2/server-side-api/` | **One profile at a time**; paywalls with remote config; virtual-currency balances and history | Profile CRUD and attributes, `setTransaction`, grant/revoke access, Refund Saver preferences, paywall remote config, virtual-currency transactions | Per-key limit not published; 429 comes with `Retry-After`. Virtual-currency create: 600/min per app |
| **Export Analytics API** | `Authorization: Api-Key <secret_key>`; optional `Adapty-Tz` header | `https://api-admin.adapty.io/api/v1/client-api/` (all POST, JSON body) | Aggregates only: charts, cohort, conversion, funnel, LTV, retention, placements export. JSON or CSV | — | **2 req/s per app, shared by all keys** |
| **Web API** | `Authorization: Api-Key <public SDK key>` (safe in a browser) | `https://api.adapty.io/api/v2/web-api/` | Paywall for a placement, **with audiences and the A/B test resolved server-side** | Record a paywall view; add attribution | Not documented |
| **Webhooks** (outbound) | Your own `Authorization` header value | Dashboard only (Integrations → Webhook). One URL for production, one for sandbox | 20 event types, pushed in near real time | — | At-least-once, **no ordering**, 10 s timeout, 9 retries over 24 h, auto-pause after repeated failures |
| **S3 / GCS export** | Bucket keys | Dashboard setup | Daily CSV at 04:00 UTC: an events table (54 columns) and a **paywall-visits table**, the only raw per-user view data | — | Daily; manual backfill for any range |
| **Attribution** (CLI `attribution`) | CLI token plus an Attribution subscription | `adapty attribution report …` | Spend, installs, ROAS, CPI, cohort and predicted metrics by campaign, adset, ad, keyword, channel, country or store | — | 10k rows, 25 metrics. **Lumen: 404 `attribution_app_not_found`** |
| **Ads Manager** (CLI `asa`) | CLI token plus a connected Apple Ads account and subscription | `adapty asa …` | Campaigns, keywords, metrics, change history | Campaigns, ad groups, keywords, automations, Apple Ads segments; `--idempotency-key` | **Lumen: 402 `ads_manager_subscription_required`** |
| **Adapty Mail API** | `Bearer <mail secret>` | `https://api-mail.adapty.io/api/v1/` | — | Ingests profiles and transaction events | Saving a Mail flow sends real email |

**Forbidden here:** a CLI login is enough to read the app's secret key through `adapty apps get`, and that key unlocks the Server-side and Export APIs. This project never runs `apps get` (see Rules).

### Server-side API v2 endpoints

Base: `https://api.adapty.io`.

| Method | Path | Purpose |
|---|---|---|
| GET / POST / PATCH / DELETE | `/api/v2/server-side-api/profile/` | Read, create, update or delete one profile. PATCH requires `installation_meta.device_id` |
| POST | `/api/v2/server-side-api/purchase/set/transaction/` | Record a purchase from any store. It **shows up in analytics, the Event Feed and every integration, including webhooks** |
| POST | `/api/v2/server-side-api/purchase/profile/grant/access-level/` | Grant access with `starts_at`/`expires_at` (`null` means lifetime). **Not counted in analytics**; sent to webhooks only |
| POST | `/api/v2/server-side-api/purchase/profile/revoke/access-level/` | Revoke now, or later with `revoke_at` |
| GET / POST | `/api/v2/server-side-api/purchase/profile/refund-saver/settings/` | Per-user refund preference and consent |
| POST | `/api/v1/sdk/purchase/stripe/token/validate/` | Validate a Stripe `sub_…` or `pi_…` and import its history. Body type: `application/vnd.api+json` |
| POST | `/api/v2/server-side-api/purchase/paddle/token/validate/` | Validate a Paddle purchase |
| GET / POST | `/api/v2/server-side-api/integration/profile/set/integration-identifiers/` | Third-party IDs: AppsFlyer, Adjust, Amplitude, Mixpanel, Firebase, OneSignal, PostHog, Branch… |
| GET | `/api/v2/server-side-api/paywalls/` and `/paywalls/{id}/` | List paywalls, or get one with its products and `remote_configs` |
| PUT | `/api/v2/server-side-api/paywalls/{id}/` | Replace **all** `remote_configs` (`[{locale, data: "<json string>"}]`) |
| GET / POST | `/api/v2/server-side-api/vc/transactions/` | Virtual-currency history (cursor paging), or credit/debit 1–20 currencies. Optional `Idempotency-Key` (UUIDv4, kept about 1 h) |
| GET | `/api/v2/server-side-api/vc/balances/` | Virtual-currency balances |

- **Profile response.** It holds `profile_id`, `customer_user_id`, `total_revenue_usd`, `segment_hash` and `custom_attributes`, plus three arrays:
  - `access_levels[]`: `expires_at`, `renewal_cancelled_at`, `billing_issue_detected_at`, grace period, `cancellation_reason`, offer;
  - `subscriptions[]`: the same fields plus `commitment.will_renew`;
  - `non_subscriptions[]`.

  There is **no event timeline**.
- **Custom attributes.** At most 30 per profile. Keys are up to 30 characters; values are strings up to 50 characters, or floats. Segments read them as `attributes__<key>@string|@float`.
- **`setTransaction`.**
  - `store` can be any custom string.
  - `store_transaction_id` is at most 50 characters. A new ID fires `subscription_renewed`; reusing an ID updates that transaction.
  - It accepts `variation_id`, so a purchase can be attributed to an A/B arm.

### Export Analytics API

Base: `https://api-admin.adapty.io/api/v1/client-api/`.

| Path | Notes |
|---|---|
| `metrics/analytics/` | `chart_id`, one of 19: `revenue, mrr, arr, arppu, arpu, subscriptions_active, subscriptions_new, subscriptions_renewal_cancelled, subscriptions_expired, trials_active, trials_new, trials_renewal_cancelled, trials_expired, grace_period, billing_issue, refund_events, refund_money, non_subscriptions, installs`. Also `period_unit`, `date_type` (`purchase_date` or `profile_install_date`) and `segmentation`. Returns gross, proceeds and net |
| `metrics/cohort/` | `period_type` (renewals or days); `value_field` (revenue, arppu, arpu, arpas, subscribers, subscriptions); `accounting_type`; `prediction_months` (3, 6, 9, 12, 18 or 24) gives predicted LTV |
| `metrics/conversion/` | `from_period` / `to_period` (no documented enum), `period_unit`, `date_type`, `segmentation` |
| `metrics/funnel/` | `show_value_as`: absolute, relative or both |
| `metrics/ltv/` | Revenue, proceeds and net LTV, with `cohort_size` |
| `metrics/retention/` | `use_trial` |
| `exports/placements/` | Per placement: audience, segment, A/B or crossplacement test, and the paywall/onboarding/flow names |

- **Filters.** Pass a `filters` object; every key takes an array. `date` is required. The rest are optional:
  - comparison: `compare_date`;
  - store and product: `store`, `country`, `store_product_id` (format `app_store:<id>`), `duration`;
  - attribution: `attribution_*` (source, status, channel, campaign, adgroup, adset, creative);
  - offer: `offer_category`, `offer_type`, `offer_id`;
  - Adapty entities: `placement_id`, `audience_id`, `paywall_id`, `flow_id`, `segment_id`, `flow_screen_id`.
- **Segmentation.** One dimension per call.
- **No A/B-test filter.** The public API has none, though the CLI can filter by A/B test.

### Web API

Base: `https://api.adapty.io/api/v2/web-api/`.

- `POST paywall/` with `{store, placement_id, locale, customer_user_id|profile_id}` returns `paywall_id`, `variation_id`, `ab_test_name`, `products[]` and `remote_config`. **Audiences and the A/B test are resolved server-side**, which makes it handy for demoing targeting without a phone.
- `POST paywall/visit/` with `{variation_id, store, visited_at}` records a view.
- `POST attribution/` with `{status, channel, campaign, ad_group, ad_set, creative, attribution_user_id}`.
- Then record the purchase with Server-side `setTransaction` plus the `variation_id`.
- **Flow placements (checked 7 Nov on Lumen `onboarding`).**
  - `paywall/` answers for a flow placement. The profile must exist first: create it with Server-side `POST profile`, or you get 404 `profile_does_not_exist`.
  - It returns the A/B test's `ab_test_name`, but **not the test's arm**. All 10 probe profiles got the same `variation_id` (`7395fd16…`) and a `scr_paywall` paywall, while the arms' variation IDs are `4074395b…` and `0b34fd94…`.
  - The A/B metric `users` did not move after these calls.
  - **Takeaway:** don't use the Web API to demo or measure flow-test assignment; use a placement of type paywall.

### Webhook events

**20 event types:**
- **Subscriptions:** `subscription_started`, `subscription_active` (synthetic), `subscription_renewed`, `subscription_renewal_cancelled`, `subscription_renewal_reactivated`, `subscription_expired`, `subscription_paused`, `subscription_deferred`, `subscription_refunded`.
- **Trials:** `trial_started`, `trial_active` (synthetic), `trial_converted`, `trial_renewal_cancelled`, `trial_renewal_reactivated`, `trial_expired`.
- **Billing:** `entered_grace_period`, `billing_issue_detected`.
- **One-time purchases:** `non_subscription_purchase`, `non_subscription_purchase_refunded`.
- **Access:** `access_level_updated` (webhook only).

**Top-level fields:** `profile_id`, `customer_user_id`, `idfv`, `idfa`, `advertising_id`, `profile_install_datetime`, `email`, `event_type`, `event_datetime`, `event_properties`, `attributions`. Optional: `user_attributes`, `integration_ids`.

**Key `event_properties`:**
- money: `price_usd`, `proceeds_usd`, `net_revenue_usd`, `tax_amount_usd`, currency;
- product and store: `vendor_product_id`, `store`, `store_country`, `environment`, `transaction_id`, `original_transaction_id`;
- subscription lifecycle: `subscription_expires_at`, `consecutive_payments`, `cancellation_reason`, `trial_duration`;
- placement and tests: `developer_id` (the placement), `paywall_name`, `variation_id`, `flow_id`, `ab_test_id`, `ab_test_name`, `ab_test_variant_name`, `cohort_name` (the audience);
- profile: `profile_country`, `profile_total_revenue_usd`, `profile_event_id` (use it to deduplicate).

**Delivery:** usually 5–60 s after the event; cancellations can take up to 2 h. Any response from 200 to 404 stops retries.

### Developer CLI

- **Self-documenting.** `adapty <topic> --help`, `adapty <topic> <cmd> --help`, and `adapty analytics catalog --app <id> --json`, which lists charts, conversions and dimensions. Detailed per-domain usage is in the installed Adapty skills.
- **Size.** 137 commands: 82 read, 55 mutate. Every command takes `--json`.
- **Topics.** `ab-tests`, `access-levels`, `analytics`, `apps`, `asa`, `attribution`, `auth`, `flows`, `migrations`, `paywalls`, `placements`, `product-groups`, `product-offers`, `product-prices`, `products`, `segments`.

## What you CANNOT do through public APIs

1. **List, search or export users.** Profiles are read one at a time by ID. For a user list, use the S3 export or build your own from webhooks.
2. **Read a per-user event timeline.** The profile has current state only. The Event Feed lives in the dashboard and keeps 2 weeks.
3. **Get webhooks for non-revenue events.** There are none for paywall or flow screen views, profile created, attribute changed or segment entered.
4. **Get push events for A/B test status.** Nothing fires on "test finished" or "test reached significance"; you have to poll.
5. **Configure integrations by API.** Webhooks, S3, MMPs, Slack, store connections and API keys are dashboard-only. There is one webhook URL per environment, so fan-out is up to you.
6. **Stream raw data.** The S3/GCS export runs daily. There is no BigQuery or Snowflake export.
7. **Get anything finer than aggregates from analytics.** One group-by dimension per call, 2 req/s per app.
8. **Delete things.** There is no delete for apps, access levels, products, offers, paywalls, flows, placements or segments. Placement type, developer ID and store product IDs can't change.
9. **Edit a legacy paywall's design.** Only `remote_configs` are editable. The legacy builders were deprecated on 1 Oct 2026; new work is Flows, which need SDK v4+.
10. **Run some A/B test types from the CLI.** Crossplacement and onboarding tests can't be created there. A running test can't be edited (Modify creates a copy). Adapty has no sample-size calculator and no stopping rule.
11. **Use OR in segments.** Conditions are AND-only. `profile_count` shows 0 at first. No command lists custom-attribute keys.
12. **See server-side grants in analytics.** Use `setTransaction` if the purchase should count.
13. **Run a new price test within the hackathon.** It needs new subscription products created in the store and approved in review.
14. **Rely on every CLI route.** Some lag the backend: 405 has been reported on `flows update` and `segments create`, and 404 on `flows publish`. Fall back to the dashboard.

## Data and CLI traps

Found on live data. These are not documented anywhere else.

**Lookups and query parameters**
- Lookups accept **UUIDs only**: `placements get main` and `access-levels get pro` both fail.
- There is no default app and no `ADAPTY_APP` env var. Pass `--app` every time.
- Dates must be absolute `YYYY-MM-DD`. `-30d` and `today` are rejected.
- Default granularity differs: `chart` and `cohort` use month, `conversion` uses day.
- Week buckets are anchored on the `--date-from` weekday, not ISO weeks. Incomplete periods are not flagged; the only exception is `has_unfinished` in conversion JSON.
- `ab-tests list` defaults to `--type flow`. Paywall tests need a second call.
- `ab-tests metrics … <id>` still requires `--type`; without it you get `ab_test_type_mismatch`.

**Output and errors**
- There are 5 different "empty" result shapes and 3 error JSON shapes (oclif, snake_case API, camelCase ASA). With `--json`, errors go to stdout.
- The CLI never retries on 429. Add backoff and a request budget: about 2 req/s per app, shared.

**Numbers that don't reconcile**
- Payer counts differ by report: new subscriptions 914, funnel "Paid" 954, LTV cohort 924, cohort subscribers 982.
- ARPPU differs too: $45.50 in the chart vs $48.36 in the cohort.
- `chart --group-by segment_id` double-counts overlapping segments ($123,736 vs $44,686).
- `ltv --group-by store` has a broken Total row.
- `refund_money` is $0 for 58 refunds.
- `conversion view-trial` / `view-paid` show 0% despite 897 views.
- The funnel is non-monotonic: paywall 897 < trial 951 < paid 954.
- For stock metrics like MRR, "Total" is the last point; for flow metrics it's the sum.
- Compare mode returns two tables and no delta.

**Product labels**
- Labels mix names (App Store) and store IDs (Play).
- Filter `store_product_id` as `app_store:<id>`, but `--group-by store_product_id` returns UUID keys.

**A/B readouts**
- P2BB compares realized revenue only, so it is biased toward up-front arms while trials and renewals are pending. On the live Onboarding test the gap is large and the dashboard is right; the trap shows on the synthetic test (`eval/synthetic_test/RESULTS.md`).
- At `--depth 3`, A/B metrics show 0 purchases at screen and product level.
- Completed tests have no winner or stop-reason field.
- Cohort predictions disappear when you filter by placement, paywall or A/B test, and need at least 30 payers per cohort.

## Prototype tricks

- **Synthetic events.** Server-side `setTransaction` on a test profile fires real webhooks and lands in analytics. Add `variation_id` to attribute the purchase to an A/B arm.
- **Targeting demo without a phone.** Call Web API `POST paywall/` for a profile before and after you change its attribute or segment.
- **Closed loop.** Webhook → your service → `PATCH profile` custom attribute → segment `attributes__x@string` → placement audience → a different flow or paywall.
- **Safe flow edits.**
  1. `flows config get`, then edit.
  2. `flows config validate`.
  3. `flows config preview`: a local render.
  4. `config update --expected-updated-at`: optimistic locking.
  5. `publish`, then poll `flows get`.
- **Joining placement → content → product.** `placements get` gives the audiences, `flows config get` the flow, `_meta.screens.*.products` its products, then `products list`.
- **Drafts are invisible.** `ab-tests create` makes a draft that no user sees.
- **Docs as markdown.** Append `.md` to any docs URL (`https://adapty.io/docs/<slug>.md`). The full index is at `https://adapty.io/docs/llms.txt`.

## Key links

- **Docs index:** https://adapty.io/docs · https://adapty.io/docs/llms.txt
- **Developer CLI:**
  - https://adapty.io/docs/developer-cli-quickstart
  - Per-topic pages: `developer-cli-reference`, `-authentication`, `-apps`, `-products`, `-paywalls`, `-flows`, `-placements`, `-analytics`, `-ab-tests`, `-attribution`, `-migrations`
- **Server-side API:** https://adapty.io/docs/getting-started-with-server-side-api · https://adapty.io/docs/server-side-api-specs · https://adapty.io/docs/api-adapty
- **Export Analytics API:** https://adapty.io/docs/export-analytics-api · https://adapty.io/docs/api-export-analytics
- **Web API:** https://adapty.io/docs/web-api · https://adapty.io/docs/api-web
- **Webhooks and exports:**
  - https://adapty.io/docs/webhook-event-types-and-fields
  - https://adapty.io/docs/set-up-webhook-integration
  - https://adapty.io/docs/events
  - https://adapty.io/docs/s3-exports
  - https://adapty.io/docs/event-feed
- **Flow Builder:**
  - https://adapty.io/docs/adapty-flow-builder
  - https://adapty.io/docs/flow-metrics
  - https://adapty.io/docs/flow-funnel
  - https://adapty.io/docs/paywall-onboarding-builder-deprecation
- **Targeting:** https://adapty.io/docs/placements · https://adapty.io/docs/segments · https://adapty.io/docs/audience
- **A/B tests:**
  - https://adapty.io/docs/ab-test-types
  - https://adapty.io/docs/results-and-metrics
  - https://adapty.io/docs/maths-behind-it
  - https://adapty.io/docs/predictions-in-ab-tests
  - https://adapty.io/docs/run_stop_ab_tests
- **Analytics:**
  - https://adapty.io/docs/overview
  - https://adapty.io/docs/charts
  - https://adapty.io/docs/analytics-cohorts
  - https://adapty.io/docs/ltv
  - https://adapty.io/docs/predicted-ltv-and-revenue
  - https://adapty.io/docs/analytics-conversion
  - https://adapty.io/docs/analytics-funnels
  - https://adapty.io/docs/analytics-retention
- **Other features:**
  - https://adapty.io/docs/profiles-crm
  - https://adapty.io/docs/refund-saver
  - https://adapty.io/docs/retention-messaging
  - https://adapty.io/docs/virtual-currencies
  - https://adapty.io/docs/autopilot
- **Separate products:** https://adapty.io/docs/adapty-user-acquisition · https://adapty.io/docs/adapty-ads-manager · https://adapty.io/docs/adapty-mail
- **Marketing site:** https://adapty.io/pricing/ (Pro: free under $5K monthly revenue, then 1%) · https://adapty.io/integrations/

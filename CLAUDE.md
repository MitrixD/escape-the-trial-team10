# CLAUDE.md — Team 10, Adapty "First Commit" hackathon

## Project context

- Event: Adapty First Commit hackathon, Belgrade, 7–8 Nov 2026. Demo deadline: **Sunday 8 Nov, 15:00**.
- Goal: build a prototype **on top of Adapty's public surfaces** (CLI, MCP, Server-side API, Export Analytics API, Web API, webhooks). We don't have Adapty's source code. Design it so Adapty could later embed it into their product: dashboard, CLI topic, MCP tool or agent skill.
- Judges ask four questions, so answer them first:
  1. Who exactly is this for, and what do they do today without it?
  2. What changes for them: money, time or risk?
  3. Why does it need Adapty? If it uses AI, why does it need AI?
  4. What is the smallest version that proves it by Sunday 15:00?
- Research notes (Russian), kept off the public remote for now:
  - [research/01-adapty-product-report.md](research/01-adapty-product-report.md): feature catalog, persona scenarios, API map and gaps, account snapshot, CLI rough edges.
  - [research/02-extension-ideas.md](research/02-extension-ideas.md): candidate ideas checked against the judges' questions.
- The team talks in Russian. Code, comments, commit messages and this file are in English.

## Hard rules

1. **The GitHub repo is PUBLIC.** Never commit or print secrets:
   - `secret_live_…` app keys;
   - the CLI token in `~/.config/adapty/config.json`;
   - webhook auth headers;
   - Mail keys.

   Keep secrets in `.env` (gitignored) and load them with env vars. `adapty apps get <id> --json` prints `secret_key` in plain text. Never echo it, log it or save it unredacted; pipe through `jq 'del(.secret_key)'` or equivalent.
2. **Treat the shared hackathon app "Lumen" as READ-ONLY.** Others write to it too: segment `[test] churn_risk >= 0.7` appeared while we explored it. Do every write in **our own sandbox app**, created with `adapty apps create`.
3. **Assume nothing can be undone.** Almost nothing can be deleted through the CLI or API. These are one-way or high-impact:
   - `ab-tests start|stop|replace|archive`: users see the change at once and it can't be undone. A test can't be restarted.
   - `placements create`: the developer ID is permanent, can't be renamed or deleted, and is unique per app across types.
   - `placements update --audiences`: **replaces every audience** on the placement.
   - `products push`: creates a **real product in App Store Connect or Play**.
   - `product-prices set`: changes **real store prices**. With `--apply-to-existing-subscribers` it hits current users.
   - `flows publish`: the app starts serving the new version.
   - `flows config update` without `--remote-configs`: wipes the stored remote configs.
   - Server API `PUT /paywalls/{id}`: overwrites **all** `remote_configs`.
   - Saving an Adapty Mail flow: **sends real emails**.
4. **Keep a human in the loop.** Before any change users can see, show an "effect card": what users see now, what they will see, who is affected, revenue at stake, and whether it is reversible. Then wait for an explicit yes. Adapty's own skills use this pattern; keep it. The MCP has no `--yes` flag, so the only safeguard there is the agent asking.
5. Don't run `adapty feedback`, `adapty skills install`, `adapty auth logout|revoke` or any mutating command on Lumen without asking the user.
6. Put temp files in `$CLAUDE_JOB_DIR/tmp` or a gitignored dir, never in `/tmp`.

## Hackathon account facts (Lumen)

### App and configuration

- **App:** "Lumen - AI Photo Editor (Hackathon)", ID `59483555-8237-45f5-aeb7-99552db3bdcd`, iOS and Android, bundle `io.adaptyhack.lumenbcf1`.
- **The data is synthetic:**
  - All config objects were created on 7 Nov around 06:27 UTC by `agent_skill_cli`.
  - Subscription history is back-filled from 10 Jul 2026.
  - About 95% of historical revenue has **no placement, flow or paywall attribution**. Placement, flow and A/B data exists **only for 7 Nov**.
  - 7 Nov has an install spike: 4,610 installs against 4 the day before. It distorts every per-install rate, ×3–8, in windows that include it.
- **Access levels:** `premium` and `pro` ("Pro (AI Studio)").
- **Products:** 6, each with an iOS and an Android SKU:
  - Premium Weekly (3-day trial)
  - Monthly
  - Annual
  - Annual (7-day trial)
  - Lifetime
  - Pro Annual – AI Studio
- **Missing product data:** the CLI shows no prices (`price_usd` = 0, `product-prices list` says "No prices.") and no offers. `product-groups list` fails with `missing_store_credentials`.
- **Segments:**
  - US & Canada (`ip_country` US, CA)
  - Europe Tier-1 (GB, DE, FR, NL, SE)
  - Payers (`total_revenue_usd` > 0)
  - `[test] churn_risk >= 0.7` (not ours)
- **Placements:** 5, all type `flow`:
  - `onboarding`
  - `main`: audiences by segment, plus an A/B test for US & Canada
  - `ai_limit_reached`
  - `settings_upgrade`
  - `win_back`: has a redundant "All users" row that points to the same flow
- **Flows:** 7, all published, **English only**, with no variables and no remote config.

### A/B tests (all flow type)

| Test | State | Notes |
|---|---|---|
| Onboarding: annual trial vs weekly first | live | Goal "60-day revenue per install". B shows P2BB 100% (p = 7.7e-9) with $1,528 vs $0. But `trials_finished = 0` and `active_trials_rate = 1`, so the lead is a trial-timing artefact |
| Main: 3 plans vs lifetime anchor (NA) | live | No signal: P2BB 33/67 |
| Settings: upgrade vs lifetime anchor | completed | Ran 0.8 s, no data, no winner field |
| AI limit: Pro vs 3 plans | draft | — |

### Headline numbers

All USD gross, UTC, history from Jul to 7 Nov 2026.

| Metric | Value |
|---|---|
| Revenue | $44,686: Jul 5.5k, Aug 11.5k, Sep 11.2k, Oct 12.5k, Nov 1–7 3.9k |
| MRR / ARR | $6,352 / $76,220 |
| Active subscriptions / active trials | 723 / 166 |
| Trial → paid | 44.2% overall. Weekly trial ≈ 48%, annual 7-day trial ≈ 35–36% |
| ARPU / ARPPU | $7.45 / $45.50 |
| LTV per payer | $48.36. Predicted $54–59 at 12 months, $61–67 at 24 months |
| Store split | App Store 61%, Play 39% |
| Country split | US 39%, DE 11%, GB 10%, CA 6%, FR 6%, JP 5%, AU 5%, BR 4%, RS 3% |

**Patterns worth building on:**
- **Refunds per month:** 3 → 12 → 17 → 22 (Jul–Oct). 32 of 58 are weekly products; Premium Weekly has 18 refunds on 170 subscriptions.
- **Renewal cancellations per month:** 6 → 33 → 57 → 62, then **102 in Nov 1–7 alone**. 46% of trials turned off auto-renew.
- **Billing issues:** 50 expirations were caused by billing issues, yet there are zero grace-period or recovery events.
- **Funnel hole on 8 Oct:** 2 installs and 0 new subscriptions.

## Programmatic surfaces

| Surface | Auth | Base / invocation | Read | Write | Limits |
|---|---|---|---|---|---|
| **Developer CLI** `adapty` (v0.18.0; `npm i -g adapty`, Node 18+) | `adapty auth login`: browser device flow. No CI token documented | `adapty <topic> <cmd> --app <id> --json` | Almost the whole dashboard (see the CLI section) | Most config, the A/B lifecycle, flows, products and prices into stores, RevenueCat migration | Analytics and metrics: **2 req/s per app, 360/min**. No auto-retry: on 429 it exits 4 with `retry_after_seconds`. Pages default to 20, max 100 |
| **Adapty MCP** | OAuth 2.1; the client needs Client ID Metadata Document support | `https://mcp.adapty.io/mcp` (Streamable HTTP) | Same as the CLI | Same as the CLI, **except `segments create/update`** | Changes go live at once. No `--yes` |
| **Server-side API v2** | `Authorization: Api-Key <secret_key>`. Profile chosen by the `adapty-customer-user-id` or `adapty-profile-id` header | `https://api.adapty.io/api/v2/server-side-api/` | **One profile at a time**; paywalls with remote config; virtual-currency balances and history | Profile CRUD and attributes, `setTransaction`, grant or revoke access, Refund Saver prefs, paywall remote config, virtual-currency transactions | Per-key limit not published; 429 comes with `Retry-After`. Virtual-currency create: 600/min per app |
| **Export Analytics API** | `Authorization: Api-Key <secret_key>`; optional `Adapty-Tz` header | `https://api-admin.adapty.io/api/v1/client-api/` (all POST, JSON body) | Aggregates only: charts, cohort, conversion, funnel, LTV, retention, placements export. JSON or CSV | — | **2 req/s per app, shared by all keys** |
| **Web API** | `Authorization: Api-Key <public SDK key>` (browser-safe) | `https://api.adapty.io/api/v2/web-api/` | The paywall for a placement, **with audiences and the A/B test resolved server-side** | Record a paywall view; add attribution | Not documented |
| **Webhooks** (outbound) | Your `Authorization` header value | Set up only in the dashboard (Integrations → Webhook), one URL each for production and sandbox | 20 events, pushed in near real time | — | At-least-once, **no ordering**, 10 s timeout, 9 retries over 24 h, auto-pause after repeated failures |
| **S3 / GCS export** | Bucket keys | Set up in the dashboard | Daily CSV at 04:00 UTC: events table (54 columns) and **paywall-visits table** (the only raw per-user view data) | — | Daily; a manual backfill for any range is possible |
| **Attribution** (CLI `attribution`) | CLI token plus an Attribution subscription | `adapty attribution report …` | Spend, installs, ROAS, CPI, cohort and predicted metrics by campaign, ad set, ad, keyword, channel, country, store | — | 10k rows, 25 metrics. **Lumen: 404 `attribution_app_not_found`** |
| **Ads Manager** (CLI `asa`) | CLI token plus a connected Apple Ads account and subscription | `adapty asa …` | Campaigns, keywords, metrics, change history | Campaigns, ad groups, keywords, automations, Apple Ads segments; `--idempotency-key` | **Lumen: 402 `ads_manager_subscription_required`** |
| **Adapty Mail** | MCP: OAuth (1 h tokens). API: `Bearer <mail secret>` | MCP `https://api-mail.adapty.io/mcp`, API `https://api-mail.adapty.io/api/v1/` | Campaigns, flows, email analytics | Campaigns, flows, segments, A/B tests; the API only ingests profiles and events | Saving a flow sends real email |

**Hack:** CLI login is enough to get the secret key (`apps get --json`), so it unlocks the Server-side and Export APIs. Keep it secret.

### Server-side API v2 endpoints

Base `https://api.adapty.io`.

| Method | Path | Purpose |
|---|---|---|
| GET / POST / PATCH / DELETE | `/api/v2/server-side-api/profile/` | Read, create, update or delete one profile. PATCH requires `installation_meta.device_id` |
| POST | `/api/v2/server-side-api/purchase/set/transaction/` | Record a purchase from any store. It **shows up in analytics, the Event Feed and every integration, webhook included** |
| POST | `/api/v2/server-side-api/purchase/profile/grant/access-level/` | Grant access with `starts_at`/`expires_at` (`null` = lifetime). **Not counted in analytics**; goes to the webhook only |
| POST | `/api/v2/server-side-api/purchase/profile/revoke/access-level/` | Revoke now, or later with `revoke_at` |
| GET / POST | `/api/v2/server-side-api/purchase/profile/refund-saver/settings/` | Per-user refund preference and consent |
| POST | `/api/v1/sdk/purchase/stripe/token/validate/` | Validate a Stripe `sub_…` or `pi_…` and import its history. Body type is `application/vnd.api+json` |
| POST | `/api/v2/server-side-api/purchase/paddle/token/validate/` | Validate a Paddle purchase |
| GET / POST | `/api/v2/server-side-api/integration/profile/set/integration-identifiers/` | Third-party IDs: AppsFlyer, Adjust, Amplitude, Mixpanel, Firebase, OneSignal, PostHog, Branch… |
| GET | `/api/v2/server-side-api/paywalls/` and `/paywalls/{id}/` | List paywalls, or get one with products and `remote_configs` |
| PUT | `/api/v2/server-side-api/paywalls/{id}/` | Replace **all** `remote_configs` (`[{locale, data: "<json string>"}]`) |
| GET / POST | `/api/v2/server-side-api/vc/transactions/` | Virtual-currency history (cursor paging) or a credit or debit of 1–20 currencies. Optional `Idempotency-Key` (UUIDv4, kept ~1 h) |
| GET | `/api/v2/server-side-api/vc/balances/` | Virtual-currency balances |

**Profile response.** It holds `profile_id`, `customer_user_id`, `total_revenue_usd`, `segment_hash` and `custom_attributes`, plus three arrays:
- `access_levels[]`: `expires_at`, `renewal_cancelled_at`, `billing_issue_detected_at`, grace period, `cancellation_reason`, offer;
- `subscriptions[]`: the same fields plus `commitment.will_renew`;
- `non_subscriptions[]`.

It does **not** hold an event timeline.

**Custom attributes.** At most 30 per profile. Keys up to 30 characters; values are strings up to 50 characters, or floats. Segments read them as `attributes__<key>@string|@float`.

**`setTransaction` notes:**
- `store` can be any custom string.
- `store_transaction_id` is at most 50 characters. A new ID fires `subscription_renewed`; the same ID updates the existing transaction.
- It accepts `variation_id`, so a purchase can be attributed to an A/B arm.

### Export Analytics API

Base `https://api-admin.adapty.io/api/v1/client-api/`. Every endpoint is POST.

| Path | Notes |
|---|---|
| `metrics/analytics/` | `chart_id` takes one of 19 values: `revenue, mrr, arr, arppu, arpu, subscriptions_active, subscriptions_new, subscriptions_renewal_cancelled, subscriptions_expired, trials_active, trials_new, trials_renewal_cancelled, trials_expired, grace_period, billing_issue, refund_events, refund_money, non_subscriptions, installs`. Also `period_unit`, `date_type` (`purchase_date` or `profile_install_date`) and `segmentation`. Returns gross, proceeds and net |
| `metrics/cohort/` | `period_type` (renewals or days), `value_field` (revenue, arppu, arpu, arpas, subscribers, subscriptions), `accounting_type`, `prediction_months` (3, 6, 9, 12, 18 or 24: predicted LTV) |
| `metrics/conversion/` | `from_period` / `to_period` (no documented enum), `period_unit`, `date_type`, `segmentation` |
| `metrics/funnel/` | `show_value_as`: absolute, relative or both |
| `metrics/ltv/` | Revenue, proceeds and net LTV with `cohort_size` |
| `metrics/retention/` | `use_trial` |
| `exports/placements/` | Per placement: audience, segment, A/B or crossplacement test, and the paywall, onboarding or flow names |

- **Filters** (a `filters` object; every key takes an array). `date` is required. The others:
  - comparison: `compare_date`;
  - store and product: `store`, `country`, `store_product_id` (format `app_store:<id>`), `duration`;
  - attribution: `attribution_*` (source, status, channel, campaign, adgroup, adset, creative);
  - offers: `offer_category`, `offer_type`, `offer_id`;
  - Adapty entities: `placement_id`, `audience_id`, `paywall_id`, `flow_id`, `segment_id`, `flow_screen_id`.
- **Segmentation.** One dimension per call.
- **Not in the public API.** There is no A/B-test filter, though the CLI can filter by A/B test.

### Web API

Base `https://api.adapty.io/api/v2/web-api/`.

- `POST paywall/` takes `{store, placement_id, locale, customer_user_id|profile_id}`. It returns `paywall_id`, `variation_id`, `ab_test_name`, `products[]` and `remote_config`. **Audiences and A/B are resolved server-side**, so this is a good way to demo targeting without a phone.
- `POST paywall/visit/` takes `{variation_id, store, visited_at}` and records a view.
- `POST attribution/` takes `{status, channel, campaign, ad_group, ad_set, creative, attribution_user_id}`.
- Then record the purchase with Server-side `setTransaction` plus `variation_id`.
- **Unverified:** whether `paywall/` serves placements of type flow. If not, use a paywall-type placement.

### Webhook events

There are 20 event types:
- **Subscriptions:** `subscription_started`, `subscription_active` (synthetic), `subscription_renewed`, `subscription_renewal_cancelled`, `subscription_renewal_reactivated`, `subscription_expired`, `subscription_paused`, `subscription_deferred`, `subscription_refunded`.
- **Trials:** `trial_started`, `trial_active` (synthetic), `trial_converted`, `trial_renewal_cancelled`, `trial_renewal_reactivated`, `trial_expired`.
- **Billing:** `entered_grace_period`, `billing_issue_detected`.
- **One-time purchases:** `non_subscription_purchase`, `non_subscription_purchase_refunded`.
- **Access:** `access_level_updated` (webhook only).

**Top-level fields:** `profile_id`, `customer_user_id`, `idfv`, `idfa`, `advertising_id`, `profile_install_datetime`, `email`, `event_type`, `event_datetime`, `event_properties`, `attributions`. Optional: `user_attributes`, `integration_ids`.

**Key `event_properties`:**
- money: `price_usd`, `proceeds_usd`, `net_revenue_usd`, `tax_amount_usd`, currency;
- product and store: `vendor_product_id`, `store`, `store_country`, `environment`, `transaction_id`, `original_transaction_id`;
- lifecycle: `subscription_expires_at`, `consecutive_payments`, `cancellation_reason`, `trial_duration`;
- where it was bought: `developer_id` (the placement), `paywall_name`, `variation_id`, `flow_id`, `ab_test_id`, `ab_test_name`, `ab_test_variant_name`, `cohort_name` (the audience);
- profile: `profile_country`, `profile_total_revenue_usd`, `profile_event_id` (use it to deduplicate).

**Delivery:** usually 5–60 s after the event; cancellations can take up to 2 h. Any 200–404 response stops retries.

### Developer CLI reference

There are 137 commands: 82 read, 55 mutate. Every command takes `--json`. The analytics, metrics and `product-prices` commands also take `--csv`.

**Exit codes:**

| Code | Meaning |
|---|---|
| 1 | Declined at the prompt |
| 2 | Bad input; nothing was sent |
| 3 | Auth or no access |
| 4 | Server refusal or throttled |
| 5 | Network |
| 6 | Irreversible command needs `--yes` in a non-interactive run |

**Command tree:**

| Topic | Commands (mutating in **bold**) |
|---|---|
| `auth` | `login`, `status` (offline), `whoami` (live), **`logout`**, **`revoke`** |
| `apps` | `list`, `get <id>` (prints `secret_key`), **`create`** (platform can't change later), **`update`** |
| `access-levels` | `list`, `get <uuid>`, **`create --sdk-id`** (the SDK ID is immutable), **`update`** |
| `products` | `list`, `get`, **`create --period … --access-level-id`**, **`update`**, **`push --store app_store\|play_store`** (creates the product in the store) |
| `product-offers` | `list --product`, `get`, **`create --type promotional\|win_back`**, **`update`** |
| `product-prices` | `list --product`, **`set`** (has `--dry-run`, `--apply-to-existing-subscribers`) |
| `product-groups` | `list --store`, **`create`** |
| `paywalls` | `list`, `get`, `placements <id>`, `metrics list/get/values`, **`create/update --product-id`** (products lock once the paywall sits in a placement) |
| `flows` | `list`, `get` (status: draft, published, dirty, publishing, publication_failed, archived), `config get`, `config validate`, `config preview <file>` (local render), `metrics list/get/values`, **`create`**, **`update`** (rename), **`config update --config-file --expected-updated-at`**, **`media upload`** (PNG, JPEG, WebP or GIF, ~2.5 MB), **`publish`** (async: poll `get`) |
| `placements` | `list --type`, `get` (audiences with priority), `metrics list/get/values`, **`create --developer-id`** (permanent), **`update --audiences`** (replaces all) |
| `segments` | `list`, `get`, **`create/update --filter field:OP:value`** (filters are ANDed) |
| `analytics` | `catalog`, `values --dimension`, `chart`, `conversion`, `funnel`, `cohort`, `ltv`, `retention` |
| `ab-tests` | `list --type flow\|paywall` (default **flow**), `get`, `metrics total/list/get/values --type` (P2BB, p-value, interval), **`create`** (draft, invisible to users), **`update`**, **`start`**, **`stop --winner\|--other\|--no-content`**, **`replace`**, **`archive`** |
| `attribution` | `metrics`, `dimensions`, `values`, `report --metrics --group-by` |
| `asa` | `whoami`, `orgs/apps/campaigns/ad-groups/keywords/negative-keywords/search-terms/ads/creatives/product-pages/automations/segments list`, `metrics`, `metrics overview`, `competitors summary`, `change-history`; plus create, update and bulk writes with `--idempotency-key` |
| `migrations` | RevenueCat migration: `list`, `current`, `status`, `steps`, `show`, **`create`**, **`use`**, **`run`**, **`close`** |
| other | **`feedback`**, **`skills install`** |

**Analytics catalog** (`adapty analytics catalog --app <id> --json`):
- **6 operations:** metrics, cohort, conversion, funnel, ltv, retention.
- **23 charts:** the 19 from the Export API, plus `billing_issue_converted`, `billing_issue_converted_revenue`, `grace_period_converted`, `grace_period_converted_revenue`.
- **14 conversions:** `install-paid`, `install-trial`, `view-trial`, `view-paid`, `trial-paid`, `paid-2period`, `2period-3period`, `3period-4period`, `4period-5period`, `paid-6month`, `paid-1year`, `paid-2year`, `billing-issue-paid`, `grace-period-paid`.
- **24 dimensions:** `country`, `store`, `audience_id`, `paywall_id`, `placement_audience_version_id`, `placement_id`, `store_product_id`, `offer_category`, `offer_type`, `offer_id`, `attribution_status`, `attribution_channel`, `attribution_campaign`, `attribution_adgroup`, `attribution_adset`, `attribution_creative`, `attribution_source`, `duration`, `renewal_period`, `cancellation_reason`, `segment_id`, `flow_id`, `flow_screen_id`, `cross_ab_test_id`.

**Segment filter fields:**
- location and device: `ip_country`, `store_country`, `locale` (2-letter), `app_version`, `app_version_on_install` (strict SemVer), `os`, `platform`, `device`, `store`;
- subscription: `subscription_state`, `paid_access_level` (UUID), `subscription_product_id`, `subscription_expiration_date`, `total_revenue_usd`;
- person and dates: `age`, `gender`, `customer_user_id`, `install_date`, `created_at`, with `*_relative` forms (`now-7d`);
- attribution: `attribution_*`;
- custom attributes: `attributes__<key>@string|@float`.

An unknown filter value is accepted and **silently matches nobody**. Segment changes take up to 20 min to reach users.

### MCP

- **Tool names.** Each tool is a CLI command with spaces and dashes turned into underscores (`ab_tests_list`, `flows_config_get`, `analytics_conversion`), and flags become parameters (`--app` becomes `app_id`). There is no official tool list.
- **Missing tools.** `segments create` and `segments update`, and probably the local-only `flows config preview`.
- **Payloads.** Large flow configs and images travel as tool arguments. Prefer the CLI for flows and bulk work.

### Adapty agent skills (installed locally)

Path: `~/.claude/plugins/marketplaces/adapty/plugin/skills/`. Each skill has a `SKILL.md` and `references/`. **Reuse them rather than duplicate them**, and know they exist because the judges built them.

| Skill | What it already does |
|---|---|
| `growth-advisor` | App audit; "why did revenue drop"; "my test ended, what next" (outcomes SHORT, FEW, NOT SETTLED, EVEN, WORKED, HELD; ~200 purchases per arm; 95% P2BB bar); next-hypothesis list from its own evidence library (`references/evidence.md`, `market-grid.csv`, `price-index.csv`); test-duration estimate. **Reactive only, and "There is no backlog to save hypotheses to yet."** |
| `ab-tests` | Full test lifecycle with effect cards. Can't create crossplacement or onboarding tests |
| `flow-generator` | Edit flow config JSON: locales, translation, screens, tabs, quiz branching; publish; attach to a placement |
| `flow-audit` | Read-only "is this flow ready for production" verdict |
| `audiences` | Segments, and the audience order on placements |
| `paywall-teardown`, `onboarding-teardown` | Conversion critique of screens and flows |
| `migrate-placements` | Move paywall placements to new flow placements |
| `adapty-integration`, `purchase-testing` | SDK integration; sandbox purchase debugging |
| `adapty-attribution`, `ads-manager`, `adapty-mail` | Attribution reports, Apple Ads, email campaigns |
| `adapty-docs` | Finds docs pages |

The dashboard's **AI Growth Advisor** (formerly Autopilot) builds growth plans, but only for App Store paywall placements.

## What you CANNOT do through public APIs

1. **List, search or export users.** Profiles are read one by one by ID. For a user list, use the S3 export or build your own from webhooks.
2. **Read a per-user event timeline.** The profile gives current state only. The Event Feed is dashboard-only and holds 2 weeks.
3. **Get webhooks for non-revenue events.** There are none for paywall or flow screen views, profile created, attribute changed or segment entered.
4. **Get push events for test status.** There is no "test finished" or "test reached significance" event; you have to poll.
5. **Configure integrations through an API.** Webhooks, S3, MMPs, Slack, store connections and API keys are dashboard-only. Only one webhook URL per environment, so fan-out is up to you.
6. **Stream raw data.** S3/GCS export runs daily. There is no BigQuery or Snowflake export.
7. **Get more than aggregates from analytics.** Group by one dimension at a time; 2 req/s per app.
8. **Delete things.** No delete for apps, access levels, products, offers, paywalls, flows, placements or segments. Placement type and developer ID can't change. Store product IDs can't change.
9. **Edit a legacy paywall's design.** Only `remote_configs` can be changed. Legacy builders were deprecated on 1 Oct 2026; new work is Flows, SDK v4+.
10. **Run crossplacement or onboarding A/B tests from the CLI or MCP.** A running test can't be edited (Modify makes a copy). There is no sample-size calculator or stopping rule.
11. **Use OR logic in segments.** Segments are AND-only. `profile_count` shows 0 at first. No command lists custom-attribute keys.
12. **See server-side grants in analytics.** Use `setTransaction` if the purchase should count.
13. **Ship a new price test quickly.** New subscription products need store creation and review, so this is not doable within the hackathon.
14. **Rely on every CLI route.** Some may lag the backend: the skills report 405 on `flows update` and `segments create`, and 404 on `flows publish`. Fall back to the dashboard.

## Data and CLI traps

Don't get fooled by these.

**Lookups and flags**
- Lookups take **UUIDs only**: `placements get main` and `access-levels get pro` fail.
- No default app and no `ADAPTY_APP` env var. Pass `--app` every time.
- Dates must be absolute `YYYY-MM-DD`; `-30d` and `today` are rejected.
- Default granularity differs: `chart` and `cohort` use month, `conversion` uses day.
- Week buckets are anchored on the `--date-from` weekday, not ISO weeks. Incomplete periods are not flagged, except `has_unfinished` in conversion JSON.
- `ab-tests list` defaults to `--type flow`; paywall tests need a second call.
- `ab-tests metrics … <id>` still requires `--type`, otherwise `ab_test_type_mismatch`.

**Output and errors**
- There are 5 different "empty" result shapes and 3 error JSON shapes: oclif, snake_case API, camelCase ASA. Under `--json`, errors go to stdout.
- The CLI never retries a 429. Add backoff and a request budget (about 2 req/s per app, shared).

**Numbers that don't add up**
- Payer counts differ by report: new subscriptions 914, funnel "Paid" 954, LTV cohort 924, cohort subscribers 982. ARPPU is $45.50 in the chart and $48.36 in the cohort.
- `chart --group-by segment_id` double-counts overlapping segments ($123,736 vs $44,686).
- `ltv --group-by store` has a broken Total row.
- `refund_money` is $0 for 58 refunds.
- `conversion view-trial` and `view-paid` show 0% despite 897 views. The funnel is non-monotonic (paywall 897 < trial 951 < paid 954).
- For stock metrics like MRR, "Total" is the last point; for flow metrics it's the sum. Compare mode returns two tables with no delta.
- Product labels mix names (App Store) and store IDs (Play). Filter `store_product_id` as `app_store:<id>`, but `--group-by store_product_id` returns UUID keys.

**Missing or hidden data**
- P2BB on trial-heavy arms compares realized revenue only, so it is wrong early (see the onboarding test).
- Cohort predictions are hidden when you filter by placement, paywall or A/B, and need ≥30 payers in the cohort.
- A/B metrics at `--depth 3` show 0 purchases at screen and product level.
- Completed tests have no winner or stop-reason field.

## Prototype tricks

- **Synthetic events.** Server-side `setTransaction` on a sandbox profile fires real webhooks and analytics. Add `variation_id` to attribute the purchase to an A/B arm.
- **Targeting demo without a phone.** Call Web API `POST paywall/` for a profile before and after you change its attribute or segment.
- **Closed loop.** Webhook → your service → `PATCH profile` custom attribute → segment `attributes__x@string` → placement audience → a different flow or paywall.
- **Safe flow edits.** `flows config get` → edit → `flows config validate` → `flows config preview` (local render) → `config update --expected-updated-at` (optimistic lock) → `publish` → poll `flows get`.
- **Joining placement → content → product.** Use `placements get` (audiences), `flows config get`, then `_meta.screens.*.products`, then `products list`.
- **Drafts are free.** `ab-tests create` makes a draft no user sees, so it is safe to create one for a proposal.
- **Docs as markdown.** Append `.md` to any docs URL (`https://adapty.io/docs/<slug>.md`). The full index is at `https://adapty.io/docs/llms.txt`.

## Building it so Adapty can embed it

- Speak Adapty's model: app → placement → audience (segment + priority) → paywall or flow → A/B test → products → access levels. Use their IDs and names, and show names, not UUIDs, in the UI.
- Shape the core as functions that map 1:1 to a **CLI topic** (`adapty <topic> <cmd> --json`) or **MCP tools**, so the same logic can ship as a skill, a CLI command or a dashboard widget.
- Be **read-only by default**. Every write goes through an effect card plus confirmation; use idempotency keys and optimistic locking where they exist; make no change you can't describe.
- Respect the shared rate limit. 2 req/s per app is also what the customer's own tooling uses, so cache and batch.
- Be honest in the UI: label synthetic or unsettled data, incomplete periods and the revenue basis (gross, proceeds or net).
- Keep secrets out of code, logs and screenshots.

## Key links

- **Docs index:** https://adapty.io/docs · https://adapty.io/docs/llms.txt
- **Developer CLI:**
  - https://adapty.io/docs/developer-cli-quickstart
  - Per-topic pages: `developer-cli-reference`, `-authentication`, `-apps`, `-products`, `-paywalls`, `-flows`, `-placements`, `-analytics`, `-ab-tests`, `-attribution`, `-migrations`
- **MCP and AI:** https://adapty.io/docs/adapty-mcp · https://adapty.io/docs/manage-adapty-with-ai · https://adapty.io/docs/mail-mcp
- **Server-side API:** https://adapty.io/docs/getting-started-with-server-side-api · https://adapty.io/docs/server-side-api-specs · https://adapty.io/docs/api-adapty
- **Export Analytics API:** https://adapty.io/docs/export-analytics-api · https://adapty.io/docs/api-export-analytics
- **Web API:** https://adapty.io/docs/web-api · https://adapty.io/docs/api-web
- **Webhooks and exports:** https://adapty.io/docs/webhook-event-types-and-fields · https://adapty.io/docs/set-up-webhook-integration · https://adapty.io/docs/events · https://adapty.io/docs/s3-exports · https://adapty.io/docs/event-feed
- **Flow Builder:** https://adapty.io/docs/adapty-flow-builder · https://adapty.io/docs/flow-metrics · https://adapty.io/docs/flow-funnel · https://adapty.io/docs/paywall-onboarding-builder-deprecation
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
- **Other features:** https://adapty.io/docs/profiles-crm · https://adapty.io/docs/refund-saver · https://adapty.io/docs/retention-messaging · https://adapty.io/docs/virtual-currencies · https://adapty.io/docs/autopilot
- **Separate products:** https://adapty.io/docs/adapty-user-acquisition · https://adapty.io/docs/adapty-ads-manager · https://adapty.io/docs/adapty-mail
- **Marketing site:** https://adapty.io/pricing/ (Pro: free under $5K monthly revenue, then 1%) · https://adapty.io/integrations/

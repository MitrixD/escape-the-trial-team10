# Per-user data for an A/B test: what Adapty can give

> **In short.** Adapty gives per-user data only one profile at a time, through daily S3 exports or through webhooks. Reading 1,000 profiles one by one is scraping, which the hackathon rules forbid, so Verdict Agent works on per-arm group counts. A per-user estimator stays a next step.


Time-boxed investigation (task 4.5). Sources: Adapty docs (s3-exports, server-side-api-specs, webhook-event-types-and-fields), CLAUDE.md "Programmatic surfaces" and "What you CANNOT do through public APIs", `adapty analytics chart --help`. No Adapty API or CLI data call was made.

## Why it matters

The verdict uses per-arm group counts, so the estimator has no within-group spread and no real user ages. Per-user revenue and install dates would give both.

## Sources

| Source | Returns | Identifies the A/B arm | Calls for a 1,000-user test | Latency | Setup | Allowed in the hackathon |
|---|---|---|---|---|---|---|
| Server-side API `GET profile` | Current state of one profile. Needs `adapty-customer-user-id` or `adapty-profile-id` | Not documented in the profile page; unverified | 1,000, one per user. No list endpoint, so the IDs must come from elsewhere | Real time, but rate limit unpublished | Secret key | No. 1,000 calls is scraping |
| Export Analytics API / CLI `analytics` | Aggregates only: charts, cohorts, conversion, funnel, LTV, retention | Yes, through the group-by or filter on the test, but only as group totals | 1 per metric and group-by | Real time, 2 req/s per app | Secret key or CLI login | Yes, in small numbers. This is what the tool uses now |
| S3 export (events table) | One row per event with `profile_id`, `customer_user_id`, `install_date`, `event_datetime`, `revenue_usd`, `proceeds_usd`, `net_revenue_usd`, `ab_test_id`, `ab_test_variant_id`, `variation_id`, `flow_variation_id` | Yes, per event | 0 API calls. Read the files from the bucket | Daily at 04:00 UTC, previous UTC day. Manual backfill for any date range | Dashboard only: AWS IAM policy and user, then Integrations -> Amazon S3 | Yes, if Max sets it up. Demo and synthetic data only, so check that Lumen data is demo before reading it |
| S3 export (paywall-visits table) | `profile_id`, `customer_user_id`, `install_date`, `paywall_showed_at`, `ab_test_name`, `ab_test_revision`, `paywall_name` | Yes, by test name and revision. This is the only table with users who saw a paywall but did not buy, so it gives the real group size | 0 API calls | Same as above | Same as above | Same as above |
| GCS export | The docs page I read covers Amazon S3 only. CLAUDE.md names GCS as a twin | Unverified | Unverified | Unverified | Dashboard | Unverified |
| Webhooks | One event per revenue event: `profile_id`, `customer_user_id` (root), `event_type`, `price_usd`, `proceeds_usd`, `net_revenue_usd`, `ab_test_id`, `variation_id` (in `event_properties`) | Yes | 0 API calls. Needs a public HTTPS endpoint that answers within 10 s and handles retries and out-of-order delivery | Near real time | Dashboard only. One URL per environment, so fan-out is ours | Yes for setup. Only future events; no history. No events for paywall views |
| CLI analytics filters and groupings | Same as the Export Analytics API: one group-by per call, 2 req/s | Group totals only | 1 per group-by value | Real time | CLI login | Yes, but it cannot approximate per-user data. A group-by on country or install date only gives coarser buckets |

## Findings

1. No public API lists or exports users. Profile reads are one call per user, so 1,000 users is 1,000 calls. That is scraping and the hackathon rules forbid it.
2. Aggregates cannot give within-group spread. Each call returns one total per group.
3. Only the S3 export (and later webhooks) holds per-user revenue with the arm. The paywall-visits table adds the non-buyers.
4. S3 export is daily, so the newest day is missing. This suits a post-test verdict, not a live peek.
5. Webhooks carry no history, and revenue events only. They need a service that runs all the time.

## Recommendation

Feasible after the hackathon: use the S3 export (GCS if its docs confirm the same tables), with webhooks as an optional live add-on.

- Setup once per app: a bucket and Integrations -> Amazon S3, then a manual backfill for the test dates.
- The estimator reads the events and paywall-visits files for the test, joins on `profile_id`, and splits by `ab_test_variant_id`.
- It would gain: per-user revenue (so a real standard deviation per arm, not an assumed one), real ages from `install_date`, and exposed-but-unpaid users from the visits table.
- Costs: AWS setup by the app owner, a one-day lag, and files with personal fields (`ip_address`, device IDs). The reader must keep only `profile_id`, dates, revenue and arm.
- Not recommended: profile reads in bulk, even after the hackathon, because of the call cost and no way to find the IDs.

Open points to check on a real export: whether `ab_test_variant_id` is set on renewals and not only on the first purchase, and the exact GCS table layout.

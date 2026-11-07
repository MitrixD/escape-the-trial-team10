# Design

## Context

See proposal.md for why and `docs/2026-11-07-verdict-agent-design.md` for the full reasoning and review history. Constraints that shape the approach:

- The public API cannot list users or return per-user event timelines; reading profiles one by one would be scraping, which the hackathon rules forbid. Live data is therefore per-arm aggregates: `ab-tests metrics total` and `analytics funnel` filtered by flow and placement, grouped by store product (verified on Lumen: arm B gives 71 trials and 35 purchases, same as the test metrics).
- Live Lumen tests contain only users who installed on 7 Nov, so every live user has the same age and live refunds and finished trials are 0. Rich behaviour (maturity over weeks, segments, refunds) exists only in the offline dataset (50,000 users, 120 days).
- A spike eval (`eval/ab_verdict_eval.py`, 7 Nov) already implements the per-user estimator and a resampling eval. It is the reference implementation.
- One person, about one day.

## Goals / Non-Goals

**Goals:**
- One verdict function shared by live mode, offline mode, CLI, MCP and eval.
- The live path and the offline path differ only in how per-arm counts are built.

**Non-Goals:**
- A dashboard UI. The JSON is ready for one; building it is a next step.
- Per-user live data, webhooks, S3 export.

## Decisions

**1. Counts, not users, as the estimator's input.** The verdict core takes, per arm, a list of groups `(state, product, age_days, n_users, received_usd_per_user)`. Mean expected revenue is the weighted sum of `received + E[future | state, product, age]`, which equals the per-user estimator's mean exactly. For P2BB the core expands groups into pseudo-users (one value per group member), which keeps the mean exact and approximates variance by ignoring spread inside a group. Offline mode builds groups from real users, so its variance is exact; a test checks both paths agree on the mean. *Alternative:* per-user input everywhere — impossible live without scraping.

**2. Calibration table from the offline dataset by default, live reads as an upgrade.** The table maps `(state, product, age) → mean future revenue to horizon`, built exactly as in the spike (`calibrate()`), from users not in the test. Live calibration from `analytics conversion` by product is attempted first; it is unverified, so the offline table is the guaranteed fallback and the output names its source. *Alternative:* live-only calibration — blocks the whole project on one unverified call.

**3. P2BB by normal approximation of the difference in means**, as in the spike's `p2bb()`. Matches what the eval already measured; Adapty's own Bayesian model is not public. *Alternative:* Beta-Gamma Bayesian model — more code, no eval evidence it helps.

**4. Python, standard library for the core; `mcp` SDK for the server; `pytest` for tests.** The spike is stdlib Python, so the core stays dependency-free and is easy to run from README. *Alternative:* TypeScript to match the Adapty CLI — rewrites working code for no gain.

**5. Adapty access through the CLI as a subprocess with `--json`.** One wrapper owns every call: it allows only read commands (`get`, `list`, `metrics`, `analytics`, `auth whoami`), spaces calls at ≥ 0.5 s, and turns a 429 into an error with the wait time. *Alternative:* Python MCP client to Adapty's MCP — needs OAuth plumbing; the CLI is already logged in.

**6. No model inside the tool.** The MCP tool description instructs the calling agent to explain the verdict using only JSON numbers. Removes the LLM key from the repo and makes the core deterministic for eval. Eval of the agent's text runs on recorded answers.

**7. Package layout.**

```
verdict_agent/
  model.py        # dataclasses for arm groups and the verdict
  calibration.py  # build/load the (state, product, age) table
  estimator.py    # expected revenue and pseudo-users from groups
  stats.py        # p2bb, two-proportion test, Welch, Bonferroni
  verdict.py      # rules, money at stake, come-back date, next step
  guardrails.py   # refunds per payer, trial cancels within product
  segments.py     # offline segment check
  offline.py      # dataset loader, as-of-day groups per arm
  adapty_cli.py   # read-only CLI wrapper
  live.py         # test ID -> arm groups via adapty_cli
  cli.py          # `python -m verdict_agent.cli`
  mcp_server.py   # stdio MCP tool
  schema.json     # output contract
tests/
eval/             # spike moved in + verdict eval
```

**8. Next-step and come-back date rules.** `come_back_on` for `early` = test start + the longest trial length among arms' products + 30 days (first monthly renewal), capped at the horizon. For `not_enough_data` = today + days until 30 events at the observed daily rate. Money at stake = |Δ expected revenue per user| × users per day × 180 × P(leader wrong), P(leader wrong) = 1 − p2bb_expected.

## Risks / Trade-offs

- [Pseudo-user variance understates spread in live mode] → Live P2BB is labelled approximate; the eval measures the offline path, and a test shows how far live and offline P2BB differ on the same offline test.
- [Live Lumen tests are one day old] → Live demo expects `early` or `confirmed`; the scenario does not promise a specific verdict.
- [Calibration from 95% unattributed history] → Calibrate by product, not by placement; eval reports calibration error.
- [Spike resamples ~900 Settings users with replacement] → Stated in README next to every eval number.
- [CLI field names differ from MCP field names] → The wrapper maps CLI JSON once, covered by a test with a recorded CLI response.
- [Pre-hackathon work] → README lists the spike eval and research as made on 7 Nov and states what was written before 10:45.

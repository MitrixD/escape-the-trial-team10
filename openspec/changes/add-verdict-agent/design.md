# Design

## Context

See proposal.md for why and `docs/2026-11-07-verdict-agent-design.md` for the full reasoning. Constraints that shape the approach:

- Per-user data from Adapty is an open question: the Server-side API reads one profile at a time, the S3/GCS export is daily and configured in the dashboard, and neither has been tried for a test's users. How to obtain it is a time-boxed investigation (task 4.5). This version uses per-arm aggregates: `ab-tests metrics total` and `analytics funnel` filtered by flow and placement, grouped by store product (verified on Lumen: arm B gives 71 trials and 35 purchases, same as the test metrics).
- The tool must work on any Adapty app, so every input comes from Adapty itself. This version reads through the Developer CLI only; other Adapty APIs (Export Analytics, Server-side) are a next step. Calibration comes from the same app's analytics (`conversion` and `ltv` by product; `cohort` has no product grouping and is not read), never from files outside Adapty.
- The tool is not tied to one app: the app ID comes from the call (`--app`, MCP `app_id`) or `ADAPTY_APP_ID` (call > environment > `.env` file; `.env` from the working directory, else the repository root), and products are mapped through the app's own catalog. Lumen is the test app for development, fixtures and the demo; its offline dataset is the eval's ground truth only.
- Live Lumen tests contain only users who installed on 7 Nov, so every live user has the same age. Behaviour over weeks exists only in the offline dataset, which the eval turns into Adapty-shaped replay bundles.
- A spike eval (`eval/ab_verdict_eval.py`, 7 Nov) and a first implementation (`feature/verdict-agent`, PR #9) exist. They are references for interfaces and for what was verified on Lumen; the first implementation calibrated from the offline dataset, which this change replaces.
- Two people, about one day. Design and process are in `docs/2026-11-07-verdict-agent-design.md` and `CLAUDE.md`.

## Goals / Non-Goals

**Goals:**
- One verdict function shared by live reads, replay, CLI, MCP and eval.
- Every input of the verdict is obtainable from Adapty for the app being judged.

**Non-Goals (next steps, listed in README):**
- Money at stake for tests with more than two arms beyond the leader and the best other arm.
- Test validity checks (SRM, dead arm).
- Guardrails (refunds, trial cancels) and segments.
- A new UI for the A/B test screen with our estimates.
- Per-arm updating of calibration from the arm's own finished trials; Adapty's lognormal P2BB model.
- Starting, stopping or changing tests.
- A demo script and the check of the agent's text (every number in Claude's answer exists in the JSON).
- A `doctor` command that checks a clean machine (CLI installed and logged in, `.env`, dependencies) and says what is missing.
- A per-user estimator instead of group counts, depending on task 4.5; reading profiles one by one is forbidden by the hackathon rules.
- Spread inside a group: live P2BB is approximate because every user of a group gets the same value.
- Other Adapty APIs (Export Analytics, Server-side) next to the Developer CLI.

## Decisions

**1. Counts, not users, as the estimator's input.** The verdict core takes, per arm, a list of groups `(status, product, age_days, n_users, received_usd_per_user)`, status in `none | trial | active | ended`. Mean expected revenue is the weighted sum of `received + E[future | status, product, age]`. For P2BB the core expands groups into pseudo-users (one value per group member), which keeps the mean exact and ignores spread inside a group. *Alternative:* per-user input — impossible without scraping.

**2. Calibration from Adapty analytics of the same app.** `Calibration` holds, per product key (the catalog UUID; `product_map_from_catalog` maps the UUID and every `<store>:<store product id>` from `products list` to it, unknown keys map to themselves): trial→paid conversion `c_P = Σ value_to / Σ value_from` over the product's rows of `analytics conversion --conversion trial-paid --group-by store_product_id` (no `c_P` when `Σ value_from = 0`); the curve `L_P(d)`, cumulative gross revenue per paying subscriber from subscription start (trial start for trial products) to day `d`, from the product's rows of `analytics ltv --group-by store_product_id` (rows of one product merged by day with a `cohort_size`-weighted mean, interpolated linearly to every day `0..h`, flat after the last point); trial length `t_P` = the first ltv day `> 0` with value `> 0` for products with trials in `conversion`, 0 for the others. The app-wide `c` and curve come from the total rows. `analytics cohort` cannot group by product and is not read. Revenue basis is gross, as Adapty returns it and as the test metrics report it. Expected future revenue to horizon `h` for a group at age `a`, with `L` the product's curve or the app curve: unconverted trial → `c_P · (L(h) − L(a))`, never below 0 (`c_P` falls back to the app rate; no rate → 0); active → `L(h) − L(a)` (may be negative only if the curve falls, e.g. refunds); `none` and `ended` → 0; 0 once `a ≥ h`. Users are assumed to start at install, so `a` is the age since install. `t_P` (default 7) is used only to expire trials. Products missing from the app's history fall back to the app curve and rate; with no curve at all the verdict is `not_enough_data` with reason `no_calibration`. `calibration_source` describes the whole calibration, not one product: `product` (at least one product has its own curve; a product without history is still valued with the app-wide rate and curve), `app` (only the app curve) or `none`. The history window excludes the test's own period when possible (date filter up to the test start). *Alternative:* the first implementation's per-user table from the offline CSV — not available on any other app; dropped. *Alternative:* `analytics cohort` per product over renewal periods — the command has no product grouping.

**3. P2BB by normal approximation of the difference in means**, as in the spike's `p2bb()`, floored to 4 decimals. *Alternative:* Beta-Gamma or Adapty's lognormal model — next step.

**4. Verdict rules.** Maturity is floored to 4 decimals like P2BB, and the rules use the floored values. Checked in order: `not_enough_data` (any arm with fewer than 30 purchases + trials, or `calibration_source = none`); `confirmed` (`p2bb_expected ≥ 0.95`); `tie` (maturity ≥ 0.80 and the upper bound of the 95% interval of |Δ expected revenue per user| is below the MDE, 5% of the leader's expected revenue per user); otherwise `keep_running`. `reason` names why: `min_events`, `no_calibration`, `pending_revenue` (maturity < 0.80) or `underpowered`. This replaces the first implementation's `early` / `tie` pair, where `tie` on an underpowered test advised changing the lever.

**5. Come-back dates.** `not_enough_data` with `min_events` → today + ceil(days to reach 30 events at the observed daily rate). `keep_running` → the later of: test start + the longest trial length among the products of the arms' `trial` groups (`t_P`, 7 for a product without a known length; 0 when no arm has a `trial` group) + 30 days; and today + days until the sample reaches the size needed to detect the current |Δ| at 95% with the current daily traffic. Capped at the horizon, never before today. `confirmed` and `tie` → `null`.

**6. Horizon is a call parameter.** Days to the horizon are passed by the caller; 60 when omitted; values below 1 are rejected. The test goal is not parsed and no `horizon_source` is reported.

**7. Python, standard library for the core; `mcp` SDK for the server; `pytest` for tests.**

**8. Adapty access through one wrapper.** `AdaptyCLI` runs the Developer CLI as a subprocess with `--json`: read-only allowlist, `apps get` denied (it returns the secret key), calls ≥ 0.5 s apart, exit 4 / 429 → stop with the wait time, account check before the first data read; a non-numeric `retry_after_seconds` means the wait is unknown. The tool needs no API keys. Other Adapty APIs (Export Analytics, Server-side) are a next step and would go through the same wrapper with the same spacing and error rules. `read_test` names the test ID when `ab-tests get` fails; `ab-tests get` scoped with `--app` is the ownership check. *Alternative:* Python MCP client to Adapty's MCP — needs OAuth plumbing.

**9. Replay instead of an offline mode.** `--replay <dir>` substitutes the wrapper's runner with one that returns recorded JSON files named by command. Everything after the wrapper is identical to live. Each bundle has `as_of.json` (`{"as_of": "YYYY-MM-DD"}`): `scripts/record_fixtures.sh` writes the recording day, `eval/make_replay.py` writes start + day; replay judges the test as of that day unless `--as-of` is passed, so a replay gives the same JSON on any day. Replay never reads `.env` or the environment: app ID and expected company are placeholders, and the account check uses the recorded `matched_expected_company` flag. Replay bundles come from `scripts/record_fixtures.sh` (live; it refuses an empty `ADAPTY_EXPECTED_COMPANY` and exits 3 without recording when `whoami` does not match) or from the eval generator (dataset → Adapty-shaped JSON for day N). The synthetic bundle for day 14 is committed in `tests/fixtures/synthetic/day14`; other days are rebuilt by `eval/make_replay.py`.

**10. No model inside the tool.** The MCP tool description instructs the calling agent to explain the verdict using only JSON numbers.

**11. Package layout.**

```
verdict_agent/
  model.py        # Group, Arm, TestData, Calibration
  stats.py        # p2bb, confidence interval of a difference in means, sample size
  calibration.py  # Calibration from Adapty analytics responses (conversion, ltv)
  estimator.py    # expected revenue and pseudo-users from groups
  verdict.py      # horizon, verdict rules, dates, JSON
  adapty_cli.py   # read-only CLI wrapper, replay runner
  live.py         # test ID -> TestData and Calibration via the wrapper
  service.py      # verdict(ab_test_id, horizon, replay, app_id, as_of) and safe_verdict
  cli.py          # python -m verdict_agent.cli
  mcp_server.py   # stdio MCP tool
  schema.json     # output contract
tests/
eval/             # spike (reference), replay generator, verdict eval, synthetic test
scripts/          # record_fixtures.sh
```

**12. Money at stake as Bayesian expected loss.** The P2BB pair (leader L, best other O) and its pseudo-user values give Δ = mean_O − mean_L with standard error `se`, as in `p2bb`. `stats.expected_positive(mu, sd)` = E[max(0, X)] for X ~ N(mu, sd) = mu·Φ(mu/sd) + sd·φ(mu/sd), and max(0, mu) when sd = 0. Per-arm traffic per day = arm users / max(1, days since start), the same days live mode uses for `users_per_day`. `cost_per_day` = traffic_O · E⁺[−Δ] + traffic_L · E⁺[Δ] (the part of today's traffic that sees the worse arm); `loss_if_ship_leader_now` = `after_days` · `users_per_day` · E⁺[Δ] (the whole traffic sees L after the stop); `cost_until_come_back` = `cost_per_day` · (come_back_on − as_of) for `keep_running`. `after_days` defaults to 180, as in the spike. `next_action` follows the verdict except for `keep_running`. When `come_back_on` is the judging day (the test has passed its horizon), waiting gives nothing, so it is `ship_leader` with `p2bb_expected` ≥ 0.80 and `ship_either` below, basis `horizon`. Otherwise it is `ship_leader` with basis `money` when `p2bb_expected` ≥ 0.80 and `loss_if_ship_leader_now < cost_until_come_back`. The 0.80 floor (`P_MONEY_MIN`) exists because a far come-back date makes the waiting cost large enough to outweigh almost any risk: without it the rule advised shipping at 0.70 (found by review, reproduced in tests). The rule is the expected-loss stopping rule (stop when the expected loss of the decision is smaller than the cost of more data), kept separate from the 95% verdict so the verdict's guarantees and eval stay unchanged. The estimate ignores calibration error, so `money` understates the uncertainty; the eval reports how often a money-based ship picks the wrong arm. *Alternative:* the spike's formula with the true gap — unknown at run time. *Alternative:* converting raw P2BB to dollars — inherits raw P2BB's bias.

## Risks / Trade-offs

- [Calibration from `conversion` and `ltv` by product: on Lumen `conversion` returned rows only for products with trials and duplicate keys per product, `ltv` reports days 0..183 only, `cohort` has no product grouping and is not read] → first task of track C records the responses; a product-key mapping normalises store keys and UUIDs; fallback to app-wide rates; honest `not_enough_data` when nothing is available.
- [Pseudo-user variance understates spread] → labelled approximate; the eval measures the error on replay bundles.
- [Live Lumen tests are one day old] → the live demo accepts any verdict; the synthetic test on replay shows the trap.

## Interfaces (fixed so tracks can be built in parallel)

Build against these names and types; a track that needs a module owned by another track uses a stub with the same signature until it lands.

```python
# verdict_agent/model.py
@dataclass(frozen=True)
class Group: status: str; product: str; age_days: float; n: int; received: float   # status: none|trial|active|ended; received = USD per user so far
@dataclass
class Arm: title: str; groups: list[Group]; purchases: int; trials: int; paid_users: int; revenue_received: float   # property users = Σ n
@dataclass
class TestData: ab_test_id: str; title: str; placement_id: str | None; started_on: date; as_of: date; users_per_day: float; arms: list[Arm]
@dataclass
class VerdictError(ValueError)   # the tool's own validation messages, shown to callers as written
@dataclass
class Calibration: trial_to_paid: dict[str, float]; renewal_value: dict[str, list[float]]; trial_days: dict[str, int]; app_trial_to_paid: float | None; app_renewal_value: list[float] | None; source: str   # renewal_value[product][d] = cumulative gross USD per paying subscriber from subscription start to day d (analytics ltv), d = 0..horizon; trial_days 0 = no trial; source: product|app|none
    def expected(self, status, product, age_days, horizon) -> float
    def source_for(self, product) -> str

# verdict_agent/stats.py
p2bb(xa, xb) -> float                                  # P(mean b > mean a), normal approximation (spike)
diff_ci(xa, xb, level=0.95) -> tuple[float, float]     # interval of mean b − mean a
users_needed(delta, sd, level=0.95, power=0.8) -> int  # per arm, to detect delta
diff_mean_se(xa, xb) -> tuple[float, float]            # mean b − mean a and its standard error (normal approximation)
expected_positive(mu, sd) -> float                     # E[max(0, X)], X ~ N(mu, sd)

# verdict_agent/calibration.py
build_from_adapty(conversion: dict, ltv: dict | None, horizon: int, product_map: dict[str, str]) -> Calibration
product_map_from_catalog(products_list: dict) -> dict[str, str]   # UUID and <store>:<store product id> -> UUID
load(path) -> Calibration; save(cal, path)

# verdict_agent/estimator.py
estimate(arm, cal, horizon) -> ArmEstimate(received, from_trials, from_renewals; property total)   # per user
pseudo_values(arm, cal, horizon) -> list[float]

# verdict_agent/verdict.py
check_horizon(horizon: int | None) -> int                                # 60 when None; raises below 1
check_after_days(after_days: int | None) -> int                          # 180 when None; raises below 1
build_verdict(test, cal, horizon=None, after_days=None) -> dict          # JSON per spec Output contract

# verdict_agent/adapty_cli.py
class AdaptyCLI(runner=subprocess.run, clock=time.monotonic, sleep=time.sleep, min_interval=0.5): run(args) -> dict; check_account(expected_company)
replay_runner(dir: Path) -> Callable                                    # returns recorded JSON by command
ReadOnlyViolation, WrongAccount, CliError, RateLimited(retry_after)

# verdict_agent/live.py
read_test(cli, app_id, test_id) -> dict                                 # the `ab-tests get` response
live_test(cli, app_id, test_id, today, products: dict | None = None, test: dict | None = None,
          trial_days: dict[str, int] | None = None) -> TestData   # reuses products / test when passed; trial_days from the calibration
live_calibration(cli, app_id, products, horizon, until: date) -> Calibration
run_live(test_id, today=None, horizon=None, replay: Path | None = None, env_path: Path | None = None,
         app_id: str | None = None, after_days: int | None = None) -> dict   # replay: today from as_of.json when None, .env not read
default_env_path() -> Path; replay_as_of(replay) -> date

# verdict_agent/service.py, cli.py, mcp_server.py
verdict(ab_test_id, horizon=None, replay=None, app_id=None, as_of=None, after_days=None) -> dict; safe_verdict(**kw) -> dict
python -m verdict_agent.cli <id> [--horizon N] [--after-days N] [--replay DIR] [--app APP_ID] [--as-of YYYY-MM-DD]
MCP tool ab_test_verdict(ab_test_id, horizon, replay, app_id, after_days)
```

## Decisions kept from the first implementation

- Thresholds: `MIN_EVENTS = 30` (purchases + trials per arm), `P_CONFIRM = 0.95`, `MATURITY_MIN = 0.80`, `MDE_SHARE = 0.05`, `DEFAULT_HORIZON = 60`, `RENEWAL_DAYS = 30`, `DEFAULT_TRIAL_DAYS = 7`.
- `confirmed` is checked before `keep_running` on purpose: the estimator exists to decide safely before revenue matures.
- Leader = highest expected total (ties → first arm); P2BB = leader vs best other arm. Maturity = Σ users·received / Σ users·total (1.0 when 0).
- Live mode: users are assumed to arrive uniformly since the test start, with no extra Adapty calls. With `D` = days since the start (at least 1), the active users of a product are spread over ages `d + 0.5` for `d = 0 … D−1`; of a product's unconverted trials with trial length `t` (`t_P`, default 7), the share `min(1, t / D)` is still in trial, spread over ages `d + 0.5` for `d = 0 … min(D, t)−1`, and the rest are `ended`; `none` users are one group. Counts per age are integers by largest remainder. Trial groups older than their product's trial length become `ended` (a guard; no-op on this output); trial→paid conversions move users to `active`; App Store and Play keys of one product are merged through the app's product catalog (`products list`), never through a hard-coded map. The test metrics are the source of truth for per-arm counts: the funnel only splits trials, conversions and purchases by product, scaled by largest remainder to the metrics `trials`, `trials_paid` and `unique_paid_subscribers`, with revenue spread over the active users so it adds up to the metrics revenue.
- Probabilities and maturity are floored to 4 decimals; a test needs at least two arms; errors never echo `.env`, `whoami` or raw Adapty stderr; only `VerdictError` messages (and the wrapper's account, rate-limit and read-only errors) are shown as written, any other exception becomes `unexpected <TypeName>`.
- Output also carries `revenue_expected_total` per arm and `expected_gap_per_user` (leader total − best other total, ≥ 0), so a caller can quote the money at stake per user without adding numbers.
- Tests that need the offline dataset (eval only) are marked `dataset` and skip when `VERDICT_DATASET` is unset.

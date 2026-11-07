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

**2. Calibration table from the offline dataset, in both modes.** The table maps `(status, product, age) → mean future revenue to horizon`, built exactly as the spike's `calibrate()`, from users not in the evaluated test. Live mode uses the same offline table, excludes the offline test whose name equals the live test title (Lumen's live users are copies of offline users), and labels the output `offline_calibration`. *Alternative:* calibrate from live `analytics conversion` by product — recorded for comparison only; merging it is a next step.

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

## Interfaces (fixed so tracks can be built in parallel)

Build against these names and types; a track that needs a module owned by another track uses a stub with the same signature until it lands.

```python
# verdict_agent/model.py
@dataclass(frozen=True)
class Group: status: str; product: str; age_days: float; n: int; received: float   # status: none|trial|active|ended; received = USD per user so far
@dataclass
class Arm: title: str; groups: list[Group]; purchases: int; trials: int; paid_users: int; refunds: int; revenue_received: float; trial_cancels: dict[str, tuple[int, int]]   # property users = Σ n
@dataclass
class TestData: ab_test_id: str; title: str; goal: str; placement_id: str | None; started_on: date; as_of: date; users_per_day: float; arms: list[Arm]; source: str; segment_rows: dict[str, list[tuple[dict[str, str], float]]] | None

# verdict_agent/stats.py
p2bb(xa, xb) -> float            # P(mean b > mean a), normal approximation (spike)
two_prop_p(k1, n1, k2, n2) -> float; welch_p(xa, xb) -> float; diff_in_diff_p(seg_a, seg_b, rest_a, rest_b) -> float; bonferroni(ps) -> list[float]

# verdict_agent/calibration.py
class Calibration(table, by_product, by_status, source): expected(status, product, age_days) -> float   # fallback (status,product,int age) -> (status,product) -> status -> 0.0
build_offline(users, exclude_test: str | None, horizon: int) -> Calibration; save(cal, path); load(path) -> Calibration

# verdict_agent/estimator.py
estimate(arm, cal) -> ArmEstimate(received, from_trials, from_renewals; property total)   # per user; total = received + Σ all groups n·expected / users
pseudo_values(arm, cal) -> list[float]

# verdict_agent/verdict.py
resolve_horizon(horizon: int | None, goal: str) -> tuple[int, str]     # parameter > goal (capped 120) > 60
build_verdict(test, cal, warnings=None, segments=None, trial_days=None, horizon=None) -> dict   # JSON per spec Output contract

# verdict_agent/guardrails.py, segments.py
warnings_for(test) -> dict[str, list[dict]]; check_segments(rows) -> tuple[int, list[dict]]

# verdict_agent/offline.py
load_users(path, horizon) -> dict; trial_days_from(users) -> dict[str, int]
offline_test(users, test_name, day, traffic, seed=7, horizon=60, cal=None) -> TestData
run_offline(path, test_name, day, traffic, seed=7, horizon=None) -> dict

# verdict_agent/adapty_cli.py, live.py
class AdaptyCLI(runner=subprocess.run, clock=time.monotonic, sleep=time.sleep, min_interval=0.5): run(args) -> dict; check_account(expected_company)
ReadOnlyViolation, WrongAccount, CliError, RateLimited(retry_after)
live_test(cli, app_id, test_id, today) -> TestData; expire_trials(test, trial_days) -> TestData; run_live(test_id, today=None, horizon=None) -> dict

# verdict_agent/service.py, cli.py, mcp_server.py
verdict(ab_test_id=None, offline_test=None, day=14, traffic=100, horizon=None) -> dict; safe_verdict(**kw) -> dict
python -m verdict_agent.cli live <id> [--horizon N] | offline "<name>" [--day] [--traffic] [--horizon]
MCP tool ab_test_verdict(ab_test_id, offline_test, day, traffic, horizon)
```

## Decisions from the first implementation

A first implementation exists on branch `feature/verdict-agent` (PR #9). These decisions came out of its reviews; keep them unless a change says otherwise.

- Thresholds: `MIN_EVENTS = 30` (purchases + trials per arm), `P_CONFIRM = 0.95`, `MATURITY_MIN = 0.80`, `GUARD_RATIO = 1.5`, `ALPHA = 0.05`, `SEGMENT_MIN_USERS = 100`, `DECISION_LIFETIME_DAYS = 180`, `DEFAULT_HORIZON = 60`, `RENEWAL_DAYS = 30`.
- `confirmed` is checked before `early` on purpose: the estimator exists to decide safely before revenue matures.
- Leader = highest expected total (ties → first arm); P2BB = leader vs best other arm. Maturity = Σ users·received / Σ users·total (1.0 when 0).
- `come_back_on`: `early` → start + longest trial (7 if unknown, 0 without trials) + 30, capped at horizon, never before today; `not_enough_data` → today + integer ceil of days to reach 30 events at the observed rate.
- Guardrails: refunds per paying user (refunded payers still count as payers); trial cancels compared only within the same product; compare with the lowest-rate other arm. `next_step.watch` lists every computed warning metric; `alternative` targets the first `worse` one.
- Segments compare the first two arms; a value needs ≥ 100 users per arm inside and outside the segment.
- Offline mode samples exactly like the spike (seeded `random.Random`, sorted arms, `traffic*day` users per arm); counts use only events at or before each user's sampled age; trial cancel = auto-renew off within 24 h of trial start (dataset's final renew status); trial length per product = median from the data.
- Live mode: product labels map to offline product keys by an explicit dict; both store segment kinds (App Store titles, Play `lumen_*`) are counted.
- Tests that need the dataset are marked `dataset` and skip when `VERDICT_DATASET` is unset; fixture regeneration only with `VERDICT_WRITE_FIXTURES=1`.
- Known open question: `tie` on Settings at day 14 (57% of runs) while 60-day truth favours `main_lifetime` — "tie" currently means "not provable yet"; splitting it into "tie" and "continue" is a candidate change.


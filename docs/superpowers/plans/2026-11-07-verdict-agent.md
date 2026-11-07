# Verdict Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only CLI command and MCP tool that take an Adapty A/B test ID and return a JSON verdict (`not_enough_data` / `confirmed` / `early` / `tie`) based on expected revenue, including revenue from pending trials and future renewals.

**Architecture:** One pure verdict core works on per-arm groups `(state, product, age, n, received)`. Two adapters build those groups: `offline.py` from the Lumen CSV dataset (demo, eval, segments) and `live.py` from the Adapty CLI (read-only aggregates). CLI and MCP are thin wrappers over the same `build_verdict()`.

**Tech Stack:** Python 3.11+ (stdlib core), `pytest`, `mcp` (Python MCP SDK, FastMCP), Adapty Developer CLI as a subprocess.

**Spec:** `openspec/changes/add-verdict-agent/` (proposal, specs, design, tasks) and `docs/2026-11-07-verdict-agent-design.md`. Reference implementation of the estimator: `../eval/ab_verdict_eval.py` (moved into `eval/` in Task 1).

## Global Constraints

- Read-only against Adapty: allowed CLI commands are `auth whoami`, `* get`, `* list`, `ab-tests metrics *`, `analytics *`. Anything else raises before running.
- Adapty calls sequential, at least 0.5 s apart; never read individual profiles; on 429 stop and report `retry_after_seconds`.
- No secrets in git. `.env` holds `LUMEN_APP_ID`, `ADAPTY_EXPECTED_COMPANY`, `VERDICT_DATASET`; `.env.example` has the keys with empty values.
- No LLM calls inside the tool. The JSON contains no model-written text.
- Thresholds: `MIN_EVENTS = 30`, `P_CONFIRM = 0.95`, `MATURITY_MIN = 0.80`, `GUARD_RATIO = 1.5`, `ALPHA = 0.05`, `SEGMENT_MIN_USERS = 100`, `DECISION_LIFETIME_DAYS = 180`, `DEFAULT_HORIZON = 60`, `RENEWAL_DAYS = 30`.
- Segment dimensions: `platform`, `acquisition_channel`, `onboarding_goal`, `push_opt_in`.
- Code, comments, commit messages in English, Conventional Commits. Add files by name; never `git add .`.
- Tests that need the offline dataset are marked `@pytest.mark.dataset` and skipped when `VERDICT_DATASET` is unset.

## Review Focus

- Test goal without a number of days → horizon 60 (Task 5).
- An arm with 0 users or 0 events → `not_enough_data`, no division by zero (Task 5).
- A test with more than two arms → leader = arm with the highest expected revenue, P2BB of leader vs the best other arm (Task 5).
- CLI not logged in or logged in to another company → clear error before any data read (Task 9).
- A live product missing from the calibration table → fallback by `(status, product)` then by `status`, never a crash (Task 3).

---

### Task 1: Project skeleton and the spike moved in

**Files:**
- Create: `verdict_agent/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `requirements.txt`, `pytest.ini`, `.env.example`, `README.md` (stub)
- Create: `eval/ab_verdict_eval.py`, `eval/money_at_stake.py`, `eval/RESULTS.md` (copied unchanged from `../eval/`)
- Modify: `.gitignore` (add `*.pem`, `*.key`, `*.p8`, `*.p12`, `.venv/`, `__pycache__/`)

**Interfaces:**
- Produces: `tests/conftest.py` fixture `dataset_path() -> pathlib.Path` (skips when `VERDICT_DATASET` unset); marker `dataset`.

- [x] **Step 1:** `python3 -m venv .venv && .venv/bin/pip install pytest mcp` and write `requirements.txt` with `pytest` and `mcp`.
- [x] **Step 2:** Copy the three spike files into `eval/`. Add a README section "Made before the hackathon core" listing them with the date 7 Nov 2026.
- [x] **Step 3:** Run `.venv/bin/python eval/ab_verdict_eval.py "$VERDICT_DATASET" 60`. Expected: the Settings block shows truth `main_lifetime=$12.60` vs `settings=$10.80`.
- [x] **Step 4:** Run `.venv/bin/pytest`. Expected: `no tests ran`. Run `git check-ignore .env`. Expected: `.env`.
- [x] **Step 5:** Commit: `chore: scaffold verdict_agent and move spike eval`.

### Task 2: Statistics

**Files:**
- Create: `verdict_agent/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Produces: `p2bb(xa: list[float], xb: list[float]) -> float` (P(mean B > mean A), normal approximation, same as spike); `two_prop_p(k1: int, n1: int, k2: int, n2: int) -> float` (two-sided); `welch_p(xa: list[float], xb: list[float]) -> float` (two-sided, normal approximation of t); `diff_in_diff_p(seg_a, seg_b, rest_a, rest_b: list[float]) -> float` (two-sided z on (mean_b−mean_a)_seg − (mean_b−mean_a)_rest); `bonferroni(ps: list[float]) -> list[float]` (min(1, p·m)).

- [x] **Step 1: Failing tests**

```python
def test_p2bb_matches_spike():
    xa, xb = [0, 0, 10, 0], [10, 10, 0, 10]
    assert p2bb(xa, xb) == pytest.approx(spike.p2bb(xa, xb))
def test_p2bb_degenerate():
    assert p2bb([1], [2]) == 0.5
def test_two_prop_equal():
    assert two_prop_p(10, 100, 10, 100) == pytest.approx(1.0)
def test_two_prop_different():
    assert two_prop_p(5, 100, 30, 100) < 0.001
def test_bonferroni_caps_at_one():
    assert bonferroni([0.03, 0.5]) == [0.06, 1.0]
```

`spike` is `eval/ab_verdict_eval.py` loaded with `importlib` (its module code only defines functions and constants).

- [x] **Step 2:** `.venv/bin/pytest tests/test_stats.py -v` → FAIL (import error).
- [x] **Step 3:** Implement the five functions in `stats.py` with `math.erf` only.
- [x] **Step 4:** Run again → PASS.
- [x] **Step 5:** Commit: `feat: add statistics helpers for verdicts`.

### Task 3: Data model and calibration

**Files:**
- Create: `verdict_agent/model.py`, `verdict_agent/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Produces in `model.py`:

```python
@dataclass(frozen=True)
class Group:
    status: str        # "none" | "trial" | "active" | "ended"
    product: str       # store product key, "-" for status "none"
    age_days: float
    n: int
    received: float   # USD received per user in this group so far

@dataclass
class Arm:
    title: str
    groups: list[Group]
    purchases: int
    trials: int
    paid_users: int
    refunds: int
    revenue_received: float                          # USD total
    trial_cancels: dict[str, tuple[int, int]]        # product -> (cancelled, started)
    @property
    def users(self) -> int: ...                      # sum of group n

@dataclass
class TestData:
    ab_test_id: str
    title: str
    goal: str
    placement_id: str | None
    started_on: date
    as_of: date
    users_per_day: float
    arms: list[Arm]
    source: str                 # "live" | "offline"
    segment_rows: dict[str, list[tuple[dict[str, str], float]]] | None  # arm -> (attrs, expected value)
```

- Produces in `calibration.py`: `class Calibration` with `expected(status: str, product: str, age_days: float) -> float`, `source: str`; `build_offline(users: dict, exclude_test: str, horizon: int) -> Calibration` (same math as spike `calibrate()`, keys `(status, product, int(age))`, fallbacks `(status, product)` then `status`, then 0.0); `save(cal, path)`, `load(path) -> Calibration`.

- [x] **Step 1: Failing tests**

```python
@pytest.mark.dataset
def test_offline_calibration_equals_spike(dataset_path):
    users = spike_load(dataset_path)               # spike.load()
    ours = build_offline(users, "Settings: upgrade vs lifetime anchor", 60)
    table, fallback = spike.calibrate([u for u in users.values() if u["test"] != "Settings: upgrade vs lifetime anchor"])
    for (st, age), v in list(table.items())[:200]:
        assert ours.expected(st[0], st[1], age) == pytest.approx(v)
def test_unknown_product_falls_back():
    cal = Calibration({("trial", "weekly", 1): 5.0}, {("trial", "weekly"): 4.0}, {"trial": 3.0}, source="test")
    assert cal.expected("trial", "unknown_product", 1) == 3.0
    assert cal.expected("ended", "x", 1) == 0.0
def test_save_load_roundtrip(tmp_path): ...       # save then load gives equal expected() on 3 keys
```

- [x] **Step 2:** Run → FAIL.
- [x] **Step 3:** Implement `model.py` and `calibration.py`. `build_offline` takes users in the spike's `load()` format, so Task 7 can reuse its loader.
- [x] **Step 4:** Run → PASS.
- [x] **Step 5:** Commit: `feat: add data model and offline calibration`.

### Task 4: Estimator from groups

**Files:**
- Create: `verdict_agent/estimator.py`
- Test: `tests/test_estimator.py`

**Interfaces:**
- Consumes: `Group`, `Arm`, `Calibration`.
- Produces: `@dataclass ArmEstimate(received: float, from_trials: float, from_renewals: float)` with property `total`, all per user; `estimate(arm: Arm, cal: Calibration) -> ArmEstimate` (`from_trials` sums groups with status `trial`, `from_renewals` sums `active`); `pseudo_values(arm: Arm, cal: Calibration) -> list[float]` (each group expanded to `n` copies of `received + cal.expected(...)`).

- [x] **Step 1: Failing tests**

```python
def test_pending_trials_raise_expected():
    cal = Calibration({}, {("trial", "annual_trial"): 20.0}, {}, source="test")
    arm = make_arm([Group("trial", "annual_trial", 0.5, 66, 0.0), Group("none", "-", 0.5, 188, 0.0)])
    est = estimate(arm, cal)
    assert est.received == 0 and est.from_trials == pytest.approx(66 * 20 / 254)
@pytest.mark.dataset
def test_groups_mean_equals_per_user_mean(dataset_path): ...
    # Settings, day 14, 100/day, seed 7: mean of spike.predict over sampled users
    # equals estimate(...).total from the groups built of the same users, within 0.01
def test_pseudo_values_length_and_mean(): ...      # len == users, mean == estimate().total
```

- [x] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [x] **Step 5:** Commit: `feat: estimate expected revenue from arm groups`.

### Task 5: Verdict rules and JSON contract

**Files:**
- Create: `verdict_agent/verdict.py`, `verdict_agent/schema.json`
- Test: `tests/test_verdict.py`

**Interfaces:**
- Consumes: `TestData`, `Calibration`, `estimate`, `pseudo_values`, `p2bb`.
- Produces: `horizon_from_goal(goal: str) -> int` (first `(\d+)-day` or `(\d+) day` in goal, else 60); `build_verdict(test: TestData, cal: Calibration, warnings: dict[str, list[dict]] | None = None, segments: tuple[int, list[dict]] | None = None) -> dict` returning exactly the JSON fields of the spec "Output contract" plus `source` and `calibration_source`.

Rules, checked in order (spec `ab-test-verdict`, "Verdict rules"):
1. any arm with `purchases + trials < 30` → `not_enough_data`;
2. leader = highest `estimate().total`; `p2bb_expected` = P2BB of leader vs best other arm on `pseudo_values` ≥ 0.95 → `confirmed`;
3. maturity = Σ received / Σ total over arms (weighted by users) < 0.80 → `early`;
4. else `tie`.

`p2bb_raw`: P2BB of the same leader on `received` only. `come_back_on`: `early` → `started_on + max trial days among arms' products + 30`, capped at `started_on + horizon`; `not_enough_data` → `as_of + ceil((30 − min events) / events per day)`; else `null`. `money_at_stake_usd` = |Δ total| × `users_per_day` × 180 × (1 − `p2bb_expected`). Next step type: `extend` / `stop_with_winner` / `extend` / `change_lever`.

- [x] **Step 1: Failing tests**, one per spec scenario, built with a `fake_test(arms_values, maturity, events)` helper:

```python
def test_not_enough_data(): assert v(fake(events=[12, 80]))["verdict"] == "not_enough_data"
def test_confident_before_maturity(): out = v(fake(p2bb=0.97, maturity=0.4)); assert out["verdict"] == "confirmed"
def test_immature_unsure(): out = v(fake(p2bb=0.7, maturity=0.5)); assert out["verdict"] == "early" and out["come_back_on"]
def test_mature_unsure(): out = v(fake(p2bb=0.7, maturity=0.9)); assert out["verdict"] == "tie" and out["next_step"]["type"] == "change_lever"
def test_horizon_from_goal(): assert horizon_from_goal("Find which onboarding offer maximises 60-day revenue per install") == 60
def test_horizon_default(): assert horizon_from_goal("lift annual share in North America") == 60
def test_equal_arms_no_money_at_stake(): assert v(fake(equal=True))["money_at_stake_usd"] == 0
def test_zero_user_arm(): assert v(fake(users=[0, 100]))["verdict"] == "not_enough_data"
def test_three_arms_leader_vs_best_other(): ...
def test_raw_and_expected_both_reported(): ...
def test_output_matches_schema(): ...              # validate keys/types against schema.json with a small stdlib checker
```

`fake(...)` builds `TestData` whose groups produce the target P2BB and maturity; keep it in `tests/helpers.py`.

- [x] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [x] **Step 5:** Commit: `feat: add verdict rules and output contract`.

### Task 6: Guardrails and segments

**Files:**
- Create: `verdict_agent/guardrails.py`, `verdict_agent/segments.py`
- Test: `tests/test_guardrails.py`, `tests/test_segments.py`

**Interfaces:**
- Produces: `warnings_for(test: TestData) -> dict[str, list[dict]]` (arm title → list of `{"metric", "value", "vs_other", "status"}`; metrics `refund_rate_per_payer`, `trial_cancel_rate:<product>`; `status = "worse"` iff ratio ≥ 1.5 and `two_prop_p` < 0.05, else `"ok"`); `check_segments(rows: dict[str, list[tuple[dict, float]]]) -> tuple[int, list[dict]]` (checked count, found list of `{"dimension", "value", "lift", "p_adjusted"}`), using `diff_in_diff_p` and `bonferroni`, skipping values with < 100 users in any arm.
- `build_verdict` gets `next_step.alternative = {"targets": metric}` when any warning is `worse`.

- [x] **Step 1: Failing tests**

```python
def test_refunds_per_user_vs_per_payer():
    # A: 1000 users, 109 payers, 12 refunds; B: 1000 users, 218 payers, 29 refunds (2.4x per user, 1.2x per payer)
    w = warnings_for(two_arm_test(...))
    assert all(x["status"] == "ok" for x in w["B"] if x["metric"] == "refund_rate_per_payer")
def test_real_refund_problem_keeps_verdict(): ...  # 2x per payer, significant -> "worse"; verdict unchanged; alternative set
@pytest.mark.dataset
def test_settings_ios_rejected(dataset_path):
    checked, found = check_segments(offline_rows("Settings: upgrade vs lifetime anchor"))
    assert checked > 0 and found == []
def test_random_segments_rejected():
    # 20 runs x 20 random binary attributes on null data (seeded): total found <= 1
```

- [x] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [x] **Step 5:** Commit: `feat: add guardrail warnings and corrected segment check`.

### Task 7: Offline mode

**Files:**
- Create: `verdict_agent/offline.py`
- Test: `tests/test_offline.py`

**Interfaces:**
- Consumes: spike loader logic (copy `load`, `rev`, `state` into `offline.py` with attributes kept: platform, acquisition_channel, onboarding_goal, push_opt_in).
- Produces: `load_users(path: Path, horizon: int) -> dict[str, dict]`; `offline_test(users, test_name: str, day: int, traffic: int, seed: int = 7, horizon: int = 60) -> TestData` (samples like the spike: `traffic * day` users per arm with ages `day − i // traffic − U(0,1)`; groups by `(status, product, floor(age))`; fills `segment_rows` with expected values; `source="offline"`, `ab_test_id = test_name`, `started_on = as_of − day`); `run_offline(path, test_name, day, traffic, seed) -> dict` (calibration from `build_offline`, warnings, segments, `build_verdict`).

- [x] **Step 1: Failing tests** (`@pytest.mark.dataset`): `offline_test(..., "Settings: upgrade vs lifetime anchor", 14, 100)` has two arms with 1400 users each; `run_offline` for Onboarding, Settings and Main at day 14 returns `source == "offline"` and a verdict in the four values; Onboarding refund warning for `onb_weekly` is `ok`.
- [x] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [x] **Step 5:** Save the three outputs to `tests/fixtures/offline_day14_*.json`. Commit: `feat: run verdicts on the offline Lumen dataset`.

### Task 8: Record live Adapty responses

**Files:**
- Create: `scripts/record_fixtures.sh`, `tests/fixtures/live/*.json`

- [x] **Step 1:** Write `scripts/record_fixtures.sh` that runs, with `sleep 1` between calls and `--json`: `adapty auth whoami`; `adapty ab-tests get <onboarding_id> --app $LUMEN_APP_ID --type flow`; `adapty ab-tests metrics total <onboarding_id> --app $LUMEN_APP_ID --type flow`; for each arm flow `adapty analytics funnel --app $LUMEN_APP_ID --date-from <start> --date-to <today> --filter flow_id=<flow> --filter placement_id=<placement> --group-by store_product_id`; `adapty analytics conversion --app $LUMEN_APP_ID --conversion trial-paid --group-by store_product_id --date-from 2026-07-01 --date-to <today>` (check exact flag names with `--help` first).
- [x] **Step 2:** Run it once. Strip `whoami` output to the company field before saving. Expected: about 7 calls, no 429.
- [x] **Step 3:** In README, note whether live calibration (`conversion` by product) returned data. If not, live mode uses the offline calibration.
- [x] **Step 4:** Commit: `test: record read-only Adapty responses for Lumen`.

### Task 9: Read-only Adapty CLI wrapper and live mode

**Files:**
- Create: `verdict_agent/adapty_cli.py`, `verdict_agent/live.py`
- Test: `tests/test_adapty_cli.py`, `tests/test_live.py`

**Interfaces:**
- Produces in `adapty_cli.py`: `class AdaptyCLI(runner=subprocess.run, clock=time.monotonic, sleep=time.sleep, min_interval=0.5)` with `run(args: list[str]) -> dict` (appends `--json`, rejects non-read commands with `ReadOnlyViolation`, spaces calls, raises `RateLimited(retry_after: int)` on exit code 4 with `retry_after_seconds`, `CliError` otherwise) and `check_account(expected_company: str) -> None` (raises `WrongAccount`).
- Produces in `live.py`: `live_test(cli: AdaptyCLI, app_id: str, test_id: str, today: date, cal: Calibration) -> TestData`. Per arm and product: `trial` group n = trials − trials paid, `active` group n = paid; `none` group n = users − subscribers; received per active user = arm revenue / paid users; age = `today − started_on`. `trial_cancels` from funnel when present, else empty. `source="live"`.

- [x] **Step 1: Failing tests** with a fake runner reading `tests/fixtures/live/`:

```python
def test_rejects_mutating_command(): pytest.raises(ReadOnlyViolation, cli.run, ["ab-tests", "stop", "x"])
def test_spacing(): ...                  # two calls -> sleep called with >= 0.5 - elapsed
def test_rate_limited(): ...             # runner returns exit 4 {"retry_after_seconds": 12} -> RateLimited(12), one call only
def test_wrong_account(): ...            # whoami company != expected -> WrongAccount before any other call
def test_onboarding_groups():
    t = live_test(fake_cli, APP, ONB_ID, date(2026, 11, 7), cal)
    assert sorted(a.users for a in t.arms) == [254, 285] and sorted(a.trials for a in t.arms) == [66, 71]
```

- [x] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [x] **Step 5:** Commit: `feat: add read-only Adapty CLI wrapper and live mode`.

### Task 10: CLI command and MCP tool

**Files:**
- Create: `verdict_agent/cli.py`, `verdict_agent/service.py`, `verdict_agent/mcp_server.py`
- Test: `tests/test_cli.py`, `tests/test_mcp.py`

**Interfaces:**
- Produces: `service.verdict(ab_test_id: str | None = None, offline_test: str | None = None, day: int = 14, traffic: int = 100, horizon: int | None = None) -> dict` (horizon precedence parameter > goal > 60, range 1–120, output field `horizon_source` = parameter | goal | default; calibration built for the same horizon; CLI flag `--horizon`, MCP tool parameter `horizon`) (live when `ab_test_id`, offline when `offline_test`; reads `.env` via a 10-line stdlib parser); `python -m verdict_agent.cli live <id>` and `python -m verdict_agent.cli offline "<name>" --day 14 --traffic 100` print JSON, exit 0, or print `{"error": ...}` and exit 1; MCP tool `ab_test_verdict` with the same parameters.
- MCP tool description (exact copy): "Read-only verdict for an Adapty A/B test. Call it before stopping a test or choosing a winner. Returns JSON only. When you explain it, use only numbers that appear in the JSON, state the verdict as given in `verdict`, and say whether the data is live or offline."

- [x] **Step 1: Failing tests:** CLI offline on Settings prints JSON with `verdict` and exits 0; unknown live ID with the fake CLI prints `{"error": ...}` and exits 1; the MCP tool handler and `service.verdict` return equal dicts for the same offline input.
- [x] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [x] **Step 5:** Run live once: `python -m verdict_agent.cli live <onboarding_id>`. Expected: JSON with `source: "live"`, fewer than 15 Adapty calls logged.
- [x] **Step 6:** Commit: `feat: expose verdict through CLI and MCP`.

### Task 11: Verdict eval

**Files:**
- Create: `eval/verdict_eval.py`
- Modify: `eval/RESULTS.md`

- [x] **Step 1:** Write `eval/verdict_eval.py`: for each of the three tests, days 1, 3, 7, 14, 21, 28, traffic 30 and 100, 150 reps (seed 7), run `run_offline` and compare with 60-day truth. Print per cell: `wrong_confirmed`, `right_confirmed`, `early_when_raw_wrong` (share of runs where raw P2BB ≥ 95% on the wrong arm and our verdict is `early` or `tie`).
- [x] **Step 2:** Add the noise-segment eval: 20 runs × 20 random attributes; print the total found.
- [x] **Step 3:** Run both. Expected: Settings day 14 at 100/day has `wrong_confirmed` ≤ 5%; noise found ≤ 1. If not, stop and report the numbers before changing any threshold.
- [x] **Step 4:** Write the tables into `eval/RESULTS.md` with the resampling limitation stated next to them.
- [x] **Step 5:** Commit: `test: add verdict eval on offline Lumen data`.

### Task 12: Agent text check and delivery

**Files:**
- Create: `AI_LOG.md`, `.mcp.json.example`, `docs/demo-script.md`
- Modify: `README.md`

- [x] **Step 1:** Register the MCP server in Claude Code (`.mcp.json.example` with `command: .venv/bin/python`, `args: ["-m", "verdict_agent.mcp_server"]`). Ask Claude three times for a verdict (live Onboarding, offline Settings day 14, offline Main day 14) and save the answers and JSON to `AI_LOG.md`.
- [x] **Step 2:** For each answer check: every number in the text appears in the JSON; the stated verdict equals `verdict`. Record pass/fail in `AI_LOG.md`.
- [x] **Step 3:** Finish README: what it does and for whom, how to run (live and offline), what is live and what is offline, architecture, eval numbers with limits, next steps, who did what, what was made before the hackathon core.
- [x] **Step 4:** Write `docs/demo-script.md` (3 minutes, live and offline parts marked) and do a timed dry run.
- [x] **Step 5:** Run `.venv/bin/pytest` and `openspec validate add-verdict-agent --strict`. Expected: both pass.
- [x] **Step 6:** Commit: `docs: add README, AI log and demo script`.

### Task 13: Repository working rules for Claude, and delivery polish

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `requirements.txt`, `verdict_agent/mcp_server.py`, `docs/superpowers/plans/2026-11-07-verdict-agent.md`, `openspec/changes/add-verdict-agent/tasks.md`
- Test: `tests/test_mcp.py`

- [x] **Step 1:** `CLAUDE.md`: add the section "How to change this project": when OpenSpec is required, tooling check, Flow A (Superpowers) and Flow B (OpenSpec only), branches, where things are, hackathon rules.
- [x] **Step 2:** `CLAUDE.md`: in the A/B tests table, replace the "artefact of trial timing" claim for "Onboarding: annual trial vs weekly first" with the eval finding: the weekly arm (B) wins at 60 and 90 days, see `eval/RESULTS.md`.
- [x] **Step 3:** Write the failing test in `tests/test_mcp.py` asserting the tool description contains "USD per user"; then append " Revenue fields in `arms` are USD per user, not totals; `money_at_stake_usd` is a total." to `DESCRIPTION`.
- [x] **Step 4:** README: "days 1–28" becomes "days 1, 3, 7, 14, 21, 28". `requirements.txt`: pin `pytest==9.2.0` and `mcp==2.3.0`.
- [x] **Step 5:** Run the full suite with `VERDICT_DATASET` exported and `openspec validate add-verdict-agent --strict`. Expected: both pass.
- [x] **Step 6:** Commit: `docs: add repository working rules for Claude`.

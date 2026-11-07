"""Live mode: read one Adapty A/B test through the read-only CLI and turn it into TestData."""
import logging
import os
from datetime import date, datetime
from pathlib import Path

from verdict_agent.adapty_cli import AdaptyCLI, CliError
from verdict_agent.calibration import Calibration, build_offline
from verdict_agent.guardrails import warnings_for
from verdict_agent.model import Arm, Group, TestData
from verdict_agent.offline import _cached_users
from verdict_agent.verdict import build_verdict, check_horizon, resolve_horizon

log = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
PRODUCTS = {
    "Premium Weekly (3-day trial)": "weekly",
    "Premium Annual (7-day trial)": "annual_trial",
    "Premium Annual": "annual",
    "Premium Monthly": "monthly",
    "lumen_weekly": "weekly",
    "lumen_annual_trial": "annual_trial",
    "lumen_annual": "annual",
    "lumen_monthly": "monthly",
    "lumen_pro_annual": "pro_annual",
    "lumen_lifetime": "lifetime",
    "lumen.weekly": "weekly",
    "lumen.annual_trial": "annual_trial",
    "lumen.annual": "annual",
    "lumen.monthly": "monthly",
    "lumen.pro_annual": "pro_annual",
    "lumen.lifetime": "lifetime",
}


def parse_env(path: Path) -> dict[str, str]:
    if not Path(path).is_file():
        return {}
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key] = value
    return env


def _steps(segment: dict) -> dict[str, int]:
    return {v["title"]: int(v["value"] or 0) for v in segment.get("values", [])}


def _product_counts(funnel: dict) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = {}
    for seg in funnel["data"]["segments"]:
        if seg.get("is_total"):
            continue
        label = seg.get("title") or seg.get("key")
        product = PRODUCTS.get(label, label)
        steps = _steps(seg)
        cell = counts.setdefault(product, [0, 0, 0])
        if "Trial" in steps:
            cell[0] += steps["Trial"]
            cell[1] += steps.get("Paid", steps.get("1 period", 0))
        else:
            cell[2] += steps.get("Paid", 0)
    return counts


def _reconcile(title: str, counts: dict[str, list[int]], target: int) -> dict[str, int]:
    trials = {p: c[0] for p, c in counts.items() if c[0]}
    seen = {p: min(counts[p][1], n) for p, n in trials.items()}
    target = min(max(0, target), sum(trials.values()))
    if sum(seen.values()) == target:
        return seen
    log.warning(
        "arm %s: funnel trial->paid %d differs from metrics trials_paid %d; scaled per product",
        title, sum(seen.values()), target,
    )
    weights = seen if sum(seen.values()) else trials
    total = sum(weights.values())
    if not total:
        return {p: 0 for p in trials}
    raw = {p: target * w / total for p, w in weights.items()}
    out = {p: min(int(v), trials[p]) for p, v in raw.items()}
    for p in sorted(raw, key=lambda p: raw[p] - int(raw[p]), reverse=True):
        if sum(out.values()) >= target:
            break
        if out[p] < trials[p]:
            out[p] += 1
    for p in sorted(trials):
        while sum(out.values()) < target and out[p] < trials[p]:
            out[p] += 1
    return out


def _live_arm(title: str, row: dict, funnel: dict, age: int) -> Arm:
    paid_users = int(row["unique_paid_subscribers"])
    revenue = float(row["revenue"] or 0)
    per_paid = revenue / max(1, paid_users)
    counts = _product_counts(funnel)
    converted = _reconcile(title, counts, int(row.get("trials_paid") or 0))
    groups = []
    for product, (trials, _, direct) in sorted(counts.items()):
        conv = converted.get(product, 0)
        if trials - conv:
            groups.append(Group("trial", product, age, trials - conv, 0.0))
        if direct + conv:
            groups.append(Group("active", product, age, direct + conv, per_paid))
    if sum(c[0] for c in counts.values()) != int(row["trials"]):
        log.warning("arm %s: per-product funnel trials do not add up to the metrics trials", title)
    if sum(g.n for g in groups if g.status == "active") != paid_users:
        log.warning("arm %s: per-product paid users do not add up to the metrics paid subscribers", title)
    none_n = int(row["users"]) - sum(g.n for g in groups)
    if none_n < 0:
        log.warning("arm %s: product groups exceed arm users by %d; none group clamped to 0", title, -none_n)
        none_n = 0
    if none_n:
        groups.append(Group("none", "-", age, none_n, 0.0))
    return Arm(
        title, groups, int(row["purchases"]), int(row["trials"]), paid_users, int(row["refunds"]), revenue, {},
    )


def live_test(cli: AdaptyCLI, app_id: str, test_id: str, today: date, cal: Calibration | None = None) -> TestData:
    try:
        test = cli.run(["ab-tests", "get", test_id, "--app", app_id])
    except CliError as exc:
        raise CliError(exc.exit_code, exc.stderr, context=f"cannot read A/B test {test_id}") from None
    test = test.get("data", test)
    placement_id = (test.get("placement") or {}).get("placement_id")
    started_on = datetime.fromisoformat(test["started_at"].replace("Z", "+00:00")).date()
    age = (today - started_on).days
    metrics = cli.run(["ab-tests", "metrics", "total", test_id, "--app", app_id, "--type", "flow"])
    rows = {r["flow_id"]: r for r in metrics["data"]["metrics"]}
    arms = []
    for flow in test["flows"]:
        row = rows[flow["flow_id"]]
        args = [
            "analytics", "funnel", "--app", app_id,
            "--date-from", started_on.isoformat(), "--date-to", today.isoformat(),
            "--filter", f"flow_id={flow['flow_id']}",
        ]
        if placement_id:
            args += ["--filter", f"placement_id={placement_id}"]
        funnel = cli.run(args + ["--group-by", "store_product_id"])
        arms.append(_live_arm(flow.get("title") or row.get("title"), row, funnel, age))
    return TestData(
        ab_test_id=test["ab_test_id"],
        title=test["title"],
        goal=test.get("goal") or "",
        placement_id=placement_id,
        started_on=started_on,
        as_of=today,
        users_per_day=sum(a.users for a in arms) / max(1, age),
        arms=arms,
        source="live",
        segment_rows=None,
    )


def environment(env_path: Path = ENV_PATH) -> dict[str, str]:
    return {**{k: v for k, v in os.environ.items() if v}, **{k: v for k, v in parse_env(env_path).items() if v}}


def run_live(
    test_id: str,
    today: date | None = None,
    *,
    cli: AdaptyCLI | None = None,
    env_path: Path = ENV_PATH,
    horizon: int | None = None,
) -> dict:
    check_horizon(horizon)
    env = environment(env_path)
    today = today or date.today()
    cli = cli or AdaptyCLI()
    cli.check_account(env.get("ADAPTY_EXPECTED_COMPANY", ""))
    app_id = env.get("LUMEN_APP_ID", "")
    if not app_id:
        raise ValueError("LUMEN_APP_ID is not set")
    dataset = env.get("VERDICT_DATASET", "")
    if not dataset:
        raise ValueError("VERDICT_DATASET is not set; it is needed for the offline calibration")
    test = live_test(cli, app_id, test_id, today)
    resolved, _ = resolve_horizon(horizon, test.goal)
    users, trial_days = _cached_users(Path(dataset), resolved)
    cal = build_offline(users, test.title, resolved)
    cal.source = "offline_calibration"
    return build_verdict(
        test, cal, warnings=warnings_for(test), segments=(0, []), trial_days=trial_days, horizon=horizon,
    )

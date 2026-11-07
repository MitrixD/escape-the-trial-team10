"""Live mode: read one Adapty A/B test through the read-only CLI and turn it into TestData."""
import logging
import os
from datetime import date, datetime
from pathlib import Path

from verdict_agent.adapty_cli import AdaptyCLI
from verdict_agent.calibration import Calibration, build_offline
from verdict_agent.guardrails import warnings_for
from verdict_agent.model import Arm, Group, TestData
from verdict_agent.offline import _cached_users
from verdict_agent.verdict import build_verdict, horizon_from_goal

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
        cell = counts.setdefault(product, [0, 0])
        cell[0] += steps.get("Trial", 0)
        cell[1] += steps.get("Paid", 0)
    return counts


def _live_arm(title: str, row: dict, funnel: dict, age: int) -> Arm:
    paid_users = int(row["unique_paid_subscribers"])
    revenue = float(row["revenue"] or 0)
    per_paid = revenue / max(1, paid_users)
    counts = _product_counts(funnel)
    groups = []
    for product, (trials, paid) in sorted(counts.items()):
        trial_n = max(0, trials - paid) if trials else 0
        if trial_n:
            groups.append(Group("trial", product, age, trial_n, 0.0))
        if paid:
            groups.append(Group("active", product, age, paid, per_paid))
    if sum(t for t, _ in counts.values()) != int(row["trials"]) or sum(p for _, p in counts.values()) != paid_users:
        log.warning("arm %s: per-product funnel counts do not add up to the metrics totals", title)
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
    test = cli.run(["ab-tests", "get", test_id, "--app", app_id])
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


def run_live(test_id: str, today: date | None = None, *, cli: AdaptyCLI | None = None, env_path: Path = ENV_PATH) -> dict:
    env = {**{k: v for k, v in os.environ.items() if v}, **{k: v for k, v in parse_env(env_path).items() if v}}
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
    horizon = horizon_from_goal(test.goal)
    users, trial_days = _cached_users(Path(dataset), horizon)
    cal = build_offline(users, None, horizon)
    cal.source = "offline_calibration"
    return build_verdict(test, cal, warnings=warnings_for(test), segments=(0, []), trial_days=trial_days)

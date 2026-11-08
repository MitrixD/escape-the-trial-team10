"""Live mode: read one Adapty A/B test and the app's history through the read-only CLI."""
import json
import logging
import os
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from verdict_agent.adapty_cli import AdaptyCLI, CliError, replay_runner
from verdict_agent.calibration import build_from_adapty, periods_from_catalog, product_map_from_catalog
from verdict_agent.model import DEFAULT_TRIAL_DAYS, Arm, Calibration, Group, TestData, VerdictError
from verdict_agent.verdict import build_verdict, check_after_days, check_horizon

log = logging.getLogger(__name__)

HISTORY_DAYS = 180
UNKNOWN = "-"
MAX_ARMS = 3
REPLAY_PLACEHOLDER = "replay"
ARM_KINDS = (("flows", "flow_id"), ("paywalls", "paywall_id"))
REPO_ENV = Path(__file__).resolve().parent.parent / ".env"
AS_OF_FILE = "as_of.json"


def read_products(cli, app_id: str) -> dict:
    return cli.run(["products", "list", "--app", app_id, "--page-size", "100"])


def label_map(products: dict) -> dict[str, str]:
    mapping = dict(product_map_from_catalog(products))
    seen: dict[str, set[str]] = {}
    for product in (products or {}).get("data") or []:
        uuid = product.get("id")
        if not uuid:
            continue
        labels = [product.get("title")]
        labels += [(v or {}).get("product_id") for v in (product.get("vendor_products") or {}).values()]
        for label in labels:
            if label:
                seen.setdefault(label, set()).add(uuid)
    for label, ids in seen.items():
        if len(ids) == 1:
            mapping.setdefault(label, next(iter(ids)))
        else:
            log.warning("product label %r belongs to several catalog products; left unmerged", label)
    return mapping


def _steps(segment: dict) -> dict[str, int]:
    values = sorted(segment.get("values") or [], key=lambda v: v.get("x") or 0)
    return {v.get("title"): int(v.get("value") or 0) for v in values}


def _product_counts(funnel: dict, labels: dict[str, str]) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = {}
    for seg in ((funnel or {}).get("data") or {}).get("segments") or []:
        if seg.get("is_total") or (seg.get("key") is None and not seg.get("title")):
            continue
        key, title = seg.get("key"), seg.get("title")
        product = labels.get(key) or labels.get(title)
        if product is None:
            product = key or title
            log.warning("funnel product %r is not in the product catalog; kept as is", product)
        steps = _steps(seg)
        cell = counts.setdefault(product, [0, 0, 0])
        if "Trial" in steps:
            cell[0] += steps["Trial"]
            cell[1] += steps.get("Paid", steps.get("1 period", 0))
        else:
            cell[2] += steps.get("Paid", 0)
    return counts


def _largest_remainder(weights: dict[str, int], target: int, caps: dict[str, int] | None = None) -> dict[str, int]:
    total = sum(weights.values())
    if target <= 0:
        return {p: 0 for p in weights}
    if not total:
        return {UNKNOWN: target}
    raw = {p: target * w / total for p, w in weights.items()}
    out = {p: int(v) for p, v in raw.items()}
    if caps is not None:
        out = {p: min(n, caps[p]) for p, n in out.items()}
    for p in sorted(raw, key=lambda p: (int(raw[p]) - raw[p], p)):
        if sum(out.values()) >= target:
            break
        if caps is None or out[p] < caps[p]:
            out[p] += 1
    for p in sorted(caps or {}):
        while sum(out.values()) < target and out[p] < caps[p]:
            out[p] += 1
    return out


def _scaled(title: str, what: str, counts: dict[str, int], target: int) -> dict[str, int]:
    if sum(counts.values()) == target:
        return dict(counts)
    log.warning("arm %s: funnel %s %d differ from the test metrics %d; scaled per product",
                title, what, sum(counts.values()), target)
    return _largest_remainder(counts, target)


def _reconcile(title: str, trials: dict[str, int], seen: dict[str, int], target: int) -> dict[str, int]:
    trials = {p: n for p, n in trials.items() if n}
    seen = {p: min(seen.get(p, 0), n) for p, n in trials.items()}
    target = min(max(0, target), sum(trials.values()))
    if sum(seen.values()) == target:
        return seen
    log.warning("arm %s: funnel trial->paid %d differs from metrics trials_paid %d; scaled per product",
                title, sum(seen.values()), target)
    weights = seen if sum(seen.values()) else trials
    return _largest_remainder(weights, target, caps=trials)


def _spread(status: str, product: str, n: int, days: int, received: float, first: int = 0,
            offset: int = 0) -> list[Group]:
    """Split n users of one status evenly over arrival days first..days-1, at ages offset + day + 0.5."""
    first = max(0, min(first, days - 1))
    span = days - first
    counts = [((2 * (d + 1) * n + span) // (2 * span)) - ((2 * d * n + span) // (2 * span)) for d in range(span)]
    return [Group(status, product, offset + first + d + 0.5, c, received) for d, c in enumerate(counts) if c]


def _trial_length(product: str, trial_days: dict[str, int], has_trials: bool) -> int:
    t = trial_days.get(product, DEFAULT_TRIAL_DAYS)
    if t == 0 and has_trials:
        log.warning("product %s: trial length unknown from the app's history but the test has trials; using %d days",
                    product, DEFAULT_TRIAL_DAYS)
        return DEFAULT_TRIAL_DAYS
    return t


def _live_arm(title: str, row: dict, funnel: dict, labels: dict[str, str], days: int,
              trial_days: dict[str, int], weight: int | None = None, offset: int = 0) -> Arm:
    paid_users = int(row.get("unique_paid_subscribers") or 0)
    revenue = float(row.get("revenue") or 0)
    metric_trials = int(row.get("trials") or 0)
    counts = _product_counts(funnel, labels)
    trials = _scaled(title, "trials", {p: c[0] for p, c in counts.items() if c[0]}, metric_trials)
    seen = {p: c[1] for p, c in counts.items()}
    converted = _reconcile(title, trials, seen, int(row.get("trials_paid") or 0))
    direct_target = max(0, paid_users - sum(converted.values()))
    direct = _scaled(title, "direct purchases", {p: c[2] for p, c in counts.items() if c[2]}, direct_target)
    active = {p: direct.get(p, 0) + converted.get(p, 0) for p in set(direct) | set(converted)}
    active_n = sum(active.values())
    if active_n != paid_users:
        log.warning("arm %s: %d converted trials exceed the metrics paid subscribers %d", title, active_n, paid_users)
    if revenue and not active_n:
        log.warning("arm %s: revenue %.2f has no paying users to carry it", title, revenue)
    per_paid = revenue / max(1, active_n)
    groups = []
    for product in sorted(set(trials) | set(active)):
        starts, conv = trials.get(product, 0), converted.get(product, 0)
        t = _trial_length(product, trial_days, starts > 0)
        still = starts - conv
        if still:
            window = min(days, max(0, t))
            pending = min(still, int(starts * window / days + 0.5)) if window else 0
            groups += _spread("trial", product, pending, window, 0.0, offset=offset) if pending else []
            if still - pending:
                groups.append(Group("ended", product, offset + days / 2, still - pending, 0.0))
        if conv:
            groups += _spread("active", product, conv, days, per_paid, first=t, offset=offset)
        if direct.get(product):
            groups += _spread("active", product, direct[product], days, per_paid, offset=offset)
    none_n = int(row.get("users") or 0) - sum(g.n for g in groups)
    if none_n < 0:
        log.warning("arm %s: product groups exceed arm users by %d; none group clamped to 0", title, -none_n)
        none_n = 0
    if none_n:
        groups.append(Group("none", UNKNOWN, offset + days / 2, none_n, 0.0))
    return Arm(title, groups, int(row.get("purchases") or 0), metric_trials, paid_users, revenue, weight)


def _arms(test: dict) -> tuple[list[dict], str]:
    for key, id_field in ARM_KINDS:
        if test.get(key):
            return test[key], id_field
    return [], "flow_id"


def _metrics_row(rows: list[dict], arm: dict, id_field: str) -> dict:
    for field in ("variation_id", id_field):
        if arm.get(field):
            match = next((r for r in rows if r.get(field) == arm[field]), None)
            if match:
                return match
    raise VerdictError(f"metrics have no row for arm {arm.get('title') or arm.get(id_field)}")


def read_test(cli, app_id: str, test_id: str) -> dict:
    try:
        test = cli.run(["ab-tests", "get", test_id, "--app", app_id])
    except CliError as exc:
        context = f"cannot read A/B test {test_id}" + (f"; {exc.context}" if exc.context else "")
        raise CliError(exc.exit_code, exc.stderr, context=context) from None
    return test.get("data", test) if isinstance(test.get("data"), dict) else test


def _started_on(test: dict) -> date:
    started = test.get("started_at")
    if not started:
        raise VerdictError(f"A/B test {test.get('ab_test_id') or ''} has not started".replace("  ", " "))
    return datetime.fromisoformat(started.replace("Z", "+00:00")).date()


def _stopped_on(test: dict) -> date | None:
    stopped = test.get("stopped_at")
    return datetime.fromisoformat(stopped.replace("Z", "+00:00")).date() if stopped else None


def live_test(cli, app_id: str, test_id: str, today: date, products: dict | None = None,
              test: dict | None = None, trial_days: dict[str, int] | None = None) -> TestData:
    if test is None:
        test = read_test(cli, app_id, test_id)
    placement_id = (test.get("placement") or {}).get("placement_id")
    start = _started_on(test)
    if (today - start).days < 0:
        raise VerdictError(f"as-of date {today.isoformat()} is before the test start {start.isoformat()}")
    stopped = _stopped_on(test)
    run_end = min(today, stopped) if stopped else today
    days = (run_end - start).days
    offset = (today - run_end).days
    arm_list, id_field = _arms(test)
    if len(arm_list) > MAX_ARMS:
        raise VerdictError("tests with more than 3 arms exceed the 10-call budget")
    test_type = test.get("type") or id_field.removesuffix("_id")
    metrics = cli.run(["ab-tests", "metrics", "total", test_id, "--app", app_id, "--type", test_type])
    rows = ((metrics or {}).get("data") or {}).get("metrics") or []
    if products is None:
        products = read_products(cli, app_id)
    labels = label_map(products)
    arms = []
    for arm in arm_list:
        row = _metrics_row(rows, arm, id_field)
        args = ["analytics", "funnel", "--app", app_id,
                "--date-from", start.isoformat(), "--date-to", run_end.isoformat(),
                "--filter", f"{id_field}={arm[id_field]}"]
        if placement_id:
            args += ["--filter", f"placement_id={placement_id}"]
        funnel = cli.run(args + ["--group-by", "store_product_id"])
        title = arm.get("title") or arm.get("flow_name") or arm.get("paywall_name") or row.get("title")
        arms.append(_live_arm(title, row, funnel, labels, max(1, days), trial_days or {}, arm.get("weight"), offset))
    return TestData(
        ab_test_id=test.get("ab_test_id", test_id),
        title=test.get("title") or "",
        placement_id=placement_id,
        started_on=start,
        as_of=today,
        users_per_day=sum(a.users for a in arms) / max(1, days),
        arms=arms,
        running_days=max(1, days),
    )


def expire_trials(test: TestData, trial_days: dict[str, int]) -> TestData:
    def expired(g: Group) -> bool:
        return g.status == "trial" and g.age_days > (trial_days.get(g.product, DEFAULT_TRIAL_DAYS) or DEFAULT_TRIAL_DAYS)

    arms = [replace(arm, groups=[Group("ended", g.product, g.age_days, g.n, 0.0) if expired(g) else g
                                 for g in arm.groups])
            for arm in test.arms]
    return replace(test, arms=arms)


def live_calibration(cli, app_id: str, products: dict | None, horizon: int, until: date) -> Calibration:
    if products is None:
        products = read_products(cli, app_id)
    window = ["--date-from", (until - timedelta(days=HISTORY_DAYS)).isoformat(),
              "--date-to", (until - timedelta(days=1)).isoformat()]
    conversion = cli.run(["analytics", "conversion", "--app", app_id, "--conversion", "trial-paid",
                          "--group-by", "store_product_id", *window])
    ltv = cli.run(["analytics", "ltv", "--app", app_id, *window,
                   "--group-by", "store_product_id", "--period-type", "days"])
    return build_from_adapty(conversion, ltv, horizon, product_map_from_catalog(products),
                             periods_from_catalog(products))


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("\"", "'") and value[0] in value[1:]:
            value = value[1:value.index(value[0], 1)]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key.strip().removeprefix("export ").strip()] = value
    return values


def default_env_path() -> Path:
    local = Path(".env")
    return local if local.is_file() else REPO_ENV


def replay_as_of(replay: Path) -> date:
    path = Path(replay) / AS_OF_FILE
    try:
        return date.fromisoformat(json.loads(path.read_text())["as_of"])
    except (OSError, ValueError, KeyError, TypeError):
        raise VerdictError(f"replay bundle has no valid {AS_OF_FILE} with the recording day; "
                           "pass --as-of YYYY-MM-DD") from None


def run_live(test_id: str, today: date | None = None, horizon: int | None = None,
             replay: Path | None = None, env_path: Path | None = None, app_id: str | None = None,
             after_days: int | None = None) -> dict:
    horizon = check_horizon(horizon)
    after_days = check_after_days(after_days)
    if replay is not None:
        today = today or replay_as_of(replay)
        cli = AdaptyCLI(runner=replay_runner(replay), min_interval=0)
        app_id, expected = REPLAY_PLACEHOLDER, REPLAY_PLACEHOLDER
    else:
        today = today or datetime.now(timezone.utc).date()
        env = {**read_env(env_path or default_env_path()), **os.environ}
        app_id = app_id or env.get("ADAPTY_APP_ID") or ""
        expected = env.get("ADAPTY_EXPECTED_COMPANY") or ""
        if not app_id:
            raise VerdictError("Adapty app id is not set: pass it in the call (--app) or set ADAPTY_APP_ID (environment or .env)")
        cli = AdaptyCLI()
    cli.check_account(expected)
    catalog = read_products(cli, app_id)
    raw = read_test(cli, app_id, test_id)
    cal = live_calibration(cli, app_id, catalog, horizon, until=_started_on(raw))
    test = live_test(cli, app_id, test_id, today, products=catalog, test=raw, trial_days=cal.trial_days)
    test = expire_trials(test, cal.trial_days)
    return build_verdict(test, cal, horizon, after_days)

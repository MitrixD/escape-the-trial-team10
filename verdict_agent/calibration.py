import json
from dataclasses import asdict
from pathlib import Path

from verdict_agent.model import Calibration


def product_map_from_catalog(products_list: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for product in (products_list or {}).get("data") or []:
        uuid = product.get("id")
        if not uuid:
            continue
        mapping[uuid] = uuid
        for store, vendor in (product.get("vendor_products") or {}).items():
            if vendor and vendor.get("product_id"):
                mapping[f"{store}:{vendor['product_id']}"] = uuid
    return mapping


def _segments(response: dict | None) -> list[dict]:
    return ((response or {}).get("data") or {}).get("segments") or []


def _product_rows(response: dict | None, product_map: dict[str, str]) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for seg in _segments(response):
        if seg.get("is_total") or seg.get("key") is None:
            continue
        rows.setdefault(product_map.get(seg["key"], seg["key"]), []).append(seg)
    return rows


def _merged_points(segments: list[dict]) -> list[tuple[float, float]]:
    by_x: dict[float, list[tuple[float, float]]] = {}
    for seg in segments:
        weight = seg.get("cohort_size") or 0
        for point in seg.get("values") or []:
            if point.get("x") is not None and point.get("value") is not None:
                by_x.setdefault(point["x"], []).append((point["value"], weight))
    points = []
    for x, pairs in sorted(by_x.items()):
        total = sum(w for _, w in pairs)
        if total > 0:
            points.append((x, sum(v * w for v, w in pairs) / total))
        else:
            points.append((x, sum(v for v, _ in pairs) / len(pairs)))
    return points


def _daily_curve(points: list[tuple[float, float]], horizon: int) -> list[float]:
    curve = []
    for d in range(horizon + 1):
        if d <= points[0][0]:
            curve.append(float(points[0][1]))
            continue
        for (x0, v0), (x1, v1) in zip(points, points[1:]):
            if x0 <= d <= x1:
                curve.append(float(v0 + (v1 - v0) * (d - x0) / (x1 - x0)))
                break
        else:
            curve.append(float(points[-1][1]))
    return curve


def _trial_length(points: list[tuple[float, float]]) -> int:
    return next((int(x) for x, v in points if x > 0 and v > 0), 0)


def periods_from_catalog(products_list: dict) -> dict[str, str]:
    return {p['id']: p['period'] for p in (products_list or {}).get('data') or [] if p.get('id') and p.get('period')}


def build_from_adapty(conversion: dict, ltv: dict | None, horizon: int, product_map: dict[str, str],
                      periods: dict[str, str] | None = None) -> Calibration:
    trials: dict[str, float] = {}
    trial_to_paid: dict[str, float] = {}
    for product, segs in _product_rows(conversion, product_map).items():
        started = sum(s.get("value_from") or 0 for s in segs)
        trials[product] = started
        if started > 0:
            trial_to_paid[product] = sum(s.get("value_to") or 0 for s in segs) / started

    data = (conversion or {}).get("data") or {}
    app_trial_to_paid = data["value_to"] / data["value_from"] if data.get("value_from") else None

    renewal_value: dict[str, list[float]] = {}
    trial_days: dict[str, int] = {}
    for product, segs in _product_rows(ltv, product_map).items():
        points = _merged_points(segs)
        if not points:
            continue
        renewal_value[product] = _daily_curve(points, horizon)
        trial_days[product] = _trial_length(points) if trials.get(product, 0) > 0 else 0

    totals = [s for s in _segments(ltv) if s.get("is_total")]
    app_points = _merged_points(totals[:1])
    app_renewal_value = _daily_curve(app_points, horizon) if app_points else None

    source = "product" if renewal_value else "app" if app_renewal_value else "none"
    return Calibration(trial_to_paid, renewal_value, trial_days, app_trial_to_paid, app_renewal_value, source,
                       dict(periods or {}))


def save(cal: Calibration, path) -> None:
    Path(path).write_text(json.dumps(asdict(cal)))


def load(path) -> Calibration:
    return Calibration(**json.loads(Path(path).read_text()))

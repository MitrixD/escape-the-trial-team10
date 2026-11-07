import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from eval.make_replay import make_replay, truth
from schema_check import assert_valid
from verdict_agent.cli import main
from verdict_agent.live import run_live

pytestmark = pytest.mark.dataset

LIVE = Path(__file__).parent / "fixtures" / "live" / "995b124f-9075-440d-83bb-20dbdf7d7fbb"
SETTINGS = "Settings: upgrade vs lifetime anchor"
DAY, TRAFFIC = 14, 100


@pytest.fixture(scope="module")
def bundle(dataset_path, tmp_path_factory):
    return make_replay(Path(dataset_path), SETTINGS, DAY, TRAFFIC, tmp_path_factory.mktemp("settings"))


def load(directory: Path) -> dict[str, dict]:
    return {p.name: json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))}


def kind(name: str) -> str:
    return "analytics_funnel_*.json" if name.startswith("analytics_funnel_") else name


def first(rows):
    return rows[0] if rows else {}


def shape(name: str, body: dict) -> dict[str, set]:
    data = body.get("data")
    out = {"top": set(body)}
    if name == "auth_whoami.json" or name == "ab-tests_get.json":
        out["flow"] = set(first(body.get("flows") or []))
        return out
    if name == "products_list.json":
        out["row"] = set(first(data))
        out["meta"] = set(body["meta"])
        return out
    out["data"] = set(data)
    if name == "ab-tests_metrics_total.json":
        out["row"] = set(first(data["metrics"]))
        return out
    segments = [s for s in data["segments"] if not s.get("is_total")]
    if name != "analytics_cohort.json":
        out["segment"] = set(first(segments))
        out["point"] = set(first(first(segments).get("values") or []))
    return out


def test_bundle_has_the_recorded_live_files_and_keys(bundle):
    ours, recorded = load(bundle), load(LIVE)
    assert sorted({kind(n) for n in ours}) == sorted({kind(n) for n in recorded})
    sample = {kind(n): (n, body) for n, body in recorded.items()}
    for name, body in ours.items():
        live_name, live_body = sample[kind(name)]
        expected = shape(live_name, live_body)
        if live_name == "analytics_cohort.json":
            expected = {"top": expected["top"], "data": expected["data"]}
        assert shape(name, body) == expected, name


def test_one_funnel_per_arm_and_arm_users_are_traffic_times_day(bundle):
    test = json.loads((bundle / "ab-tests_get.json").read_text())
    rows = json.loads((bundle / "ab-tests_metrics_total.json").read_text())["data"]["metrics"]
    flows = [f["flow_id"] for f in test["flows"]]
    assert flows == sorted(flows) and len(flows) == 2
    assert sorted(p.name for p in bundle.glob("analytics_funnel_*.json")) == [f"analytics_funnel_{f}.json" for f in flows]
    assert [r["users"] for r in rows] == [TRAFFIC * DAY] * 2
    assert test["started_at"].startswith((date(2026, 11, 3) - timedelta(days=DAY)).isoformat())


def test_funnel_counts_match_the_metrics(bundle):
    test = json.loads((bundle / "ab-tests_get.json").read_text())
    rows = json.loads((bundle / "ab-tests_metrics_total.json").read_text())["data"]["metrics"]
    for flow, row in zip(test["flows"], rows):
        funnel = json.loads((bundle / f"analytics_funnel_{flow['flow_id']}.json").read_text())
        trials = paid = 0
        for seg in funnel["data"]["segments"]:
            if seg["is_total"]:
                continue
            steps = {v["x"]: v for v in seg["values"]}
            if steps[0]["title"] == "Trial":
                trials += steps[0]["value"]
            paid += steps[1]["value"]
        assert trials == row["trials"]
        assert paid == row["unique_paid_subscribers"]


def test_catalog_ids_are_product_names_with_store_ids(bundle):
    products = json.loads((bundle / "products_list.json").read_text())["data"]
    assert products and all(p["id"] == p["title"] for p in products)
    assert all(p["vendor_products"]["app_store"]["product_id"] for p in products)


def test_same_inputs_give_byte_identical_files(dataset_path, bundle, tmp_path):
    again = make_replay(Path(dataset_path), SETTINGS, DAY, TRAFFIC, tmp_path / "again")
    ours = {p.name: p.read_bytes() for p in bundle.iterdir()}
    assert {p.name: p.read_bytes() for p in again.iterdir()} == ours


def test_run_live_on_the_bundle_gives_a_valid_verdict(bundle, tmp_path):
    test = json.loads((bundle / "ab-tests_get.json").read_text())
    as_of = date(2026, 11, 3)
    out = run_live(test["ab_test_id"], today=as_of, replay=bundle, env_path=tmp_path / "missing.env")
    assert_valid(out)
    assert [a["users"] for a in out["arms"]] == [TRAFFIC * DAY] * 2


def test_cli_replay_on_the_bundle_gives_a_valid_verdict(dataset_path, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    today = datetime.now(timezone.utc).date()
    out_dir = make_replay(Path(dataset_path), SETTINGS, DAY, TRAFFIC, tmp_path / "cli", start=today - timedelta(days=DAY))
    test = json.loads((out_dir / "ab-tests_get.json").read_text())
    code = main([test["ab_test_id"], "--replay", str(out_dir)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0, out
    assert_valid(out)
    assert [a["users"] for a in out["arms"]] == [TRAFFIC * DAY] * 2


def test_truth_is_net_revenue_per_user_for_each_arm(dataset_path):
    result = truth(Path(dataset_path), SETTINGS)
    assert sorted(result) == ["main_lifetime", "settings"]
    assert all(v > 0 for v in result.values())

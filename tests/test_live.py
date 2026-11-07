import json
from datetime import date

import pytest

from tests.live_fakes import APP, COMPANY, FIXTURES, ONB_ID, FakeRunner
from verdict_agent.adapty_cli import AdaptyCLI, WrongAccount
from verdict_agent.calibration import Calibration
from verdict_agent.live import PRODUCTS, live_test, parse_env, run_live

TODAY = date(2026, 11, 7)


def fake_cli(runner=None):
    return AdaptyCLI(runner=runner or FakeRunner(), clock=lambda: 0.0, sleep=lambda s: None, min_interval=0)


def stub_cal():
    return Calibration({}, {}, {"trial": 10.0, "active": 5.0, "none": 1.0}, "offline_calibration")


def metrics_rows():
    return {r["title"]: r for r in json.loads((FIXTURES / "ab_test_metrics_total.json").read_text())["data"]["metrics"]}


def test_onboarding_groups():
    t = live_test(fake_cli(), APP, ONB_ID, TODAY, stub_cal())
    assert sorted(a.users for a in t.arms) == [254, 285] and sorted(a.trials for a in t.arms) == [66, 71]
    assert t.source == "live"
    assert t.title == "Onboarding: annual trial vs weekly first"
    assert t.placement_id == "a0876118-9ad3-4d77-adce-c89f9ee874aa"
    assert t.goal == "Find which onboarding offer maximises 60-day revenue per install"
    assert t.started_on == date(2026, 11, 7) and t.as_of == TODAY
    assert t.users_per_day == 539
    assert t.segment_rows is None


def test_per_product_sums_match_metrics_totals():
    t = live_test(fake_cli(), APP, ONB_ID, TODAY, stub_cal())
    rows = metrics_rows()
    for arm in t.arms:
        row = rows[arm.title]
        by = {s: sum(g.n for g in arm.groups if g.status == s) for s in ("trial", "active", "none")}
        assert by["active"] == row["unique_paid_subscribers"] == arm.paid_users
        assert by["trial"] == row["trials"] - row["trials_paid"]
        assert arm.users == row["users"]
        assert by["none"] == row["users"] - row["trials"] - row["unique_paid_subscribers"]
        assert arm.purchases == row["purchases"] and arm.refunds == row["refunds"]
        assert arm.revenue_received == pytest.approx(row["revenue"])
        assert arm.trial_cancels == {}


def test_products_mapped_and_received_per_active_user():
    t = live_test(fake_cli(), APP, ONB_ID, TODAY, stub_cal())
    arms = {a.title: a for a in t.arms}
    a = {(g.status, g.product): g.n for g in arms["A"].groups}
    assert a == {("trial", "annual_trial"): 47, ("trial", "weekly"): 19, ("none", "-"): 188}
    b = {(g.status, g.product): g for g in arms["B"].groups}
    assert {k: g.n for k, g in b.items()} == {("trial", "weekly"): 71, ("active", "annual"): 35, ("none", "-"): 179}
    assert b[("active", "annual")].received == pytest.approx(1527.9004004819967 / 35)
    assert b[("trial", "weekly")].received == 0 and b[("none", "-")].received == 0
    assert all(g.age_days == 0 for g in arms["B"].groups)


def test_age_and_users_per_day_after_start():
    t = live_test(fake_cli(), APP, ONB_ID, date(2026, 11, 17), stub_cal())
    assert {g.age_days for a in t.arms for g in a.groups} == {10}
    assert t.users_per_day == pytest.approx(53.9)


def test_live_reads_are_read_only_and_filtered_by_placement():
    runner = FakeRunner()
    live_test(fake_cli(runner), APP, ONB_ID, TODAY, stub_cal())
    funnels = [c for c in runner.calls if c[1:3] == ["analytics", "funnel"]]
    assert len(funnels) == 2
    for c in funnels:
        assert "placement_id=a0876118-9ad3-4d77-adce-c89f9ee874aa" in c
        assert "--group-by" in c and "store_product_id" in c
    assert all(c[-1] == "--json" for c in runner.calls)


def test_unknown_product_label_passes_through():
    assert PRODUCTS["lumen_weekly"] == "weekly"
    assert PRODUCTS["Premium Annual (7-day trial)"] == "annual_trial"
    assert "Something New" not in PRODUCTS


def test_parse_env(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# c\nA=1\nB="two words"\nC=\'x=y\'\n\nexport D=4\nE=\n')
    assert parse_env(p) == {"A": "1", "B": "two words", "C": "x=y", "D": "4", "E": ""}
    assert parse_env(tmp_path / "missing") == {}


def test_run_live_stops_on_wrong_account_before_reads(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"LUMEN_APP_ID={APP}\nADAPTY_EXPECTED_COMPANY=Another Company\nVERDICT_DATASET=/nowhere\n")
    runner = FakeRunner()
    with pytest.raises(WrongAccount):
        run_live(ONB_ID, TODAY, cli=fake_cli(runner), env_path=env)
    assert [c[1:3] for c in runner.calls] == [["auth", "whoami"]]


@pytest.mark.dataset
def test_run_live_end_to_end(tmp_path, dataset_path):
    env = tmp_path / ".env"
    env.write_text(f'LUMEN_APP_ID={APP}\nADAPTY_EXPECTED_COMPANY="{COMPANY}"\nVERDICT_DATASET="{dataset_path}"\n')
    out = run_live(ONB_ID, TODAY, cli=fake_cli(), env_path=env)
    assert out["source"] == "live" and out["calibration_source"] == "offline_calibration"
    assert sorted(a["users"] for a in out["arms"]) == [254, 285]
    assert out["next_step"]["placement_id"] == "a0876118-9ad3-4d77-adce-c89f9ee874aa"
    assert out["segments_checked"] == 0 and out["segments_found"] == []


@pytest.mark.dataset
def test_run_live_reads_each_endpoint_once(tmp_path, dataset_path):
    env = tmp_path / ".env"
    env.write_text(f"LUMEN_APP_ID={APP}\nADAPTY_EXPECTED_COMPANY={COMPANY}\nVERDICT_DATASET={dataset_path}\n")
    runner = FakeRunner()
    out = run_live(ONB_ID, TODAY, cli=fake_cli(runner), env_path=env)
    assert [c[1:3] for c in runner.calls] == [
        ["auth", "whoami"], ["ab-tests", "get"], ["ab-tests", "metrics"], ["analytics", "funnel"], ["analytics", "funnel"],
    ]
    from tests.test_verdict import SCHEMA, check
    check(out, SCHEMA)

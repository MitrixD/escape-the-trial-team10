import json
import logging
from datetime import date

import pytest

from tests.live_fakes import APP, COMPANY, FIXTURES, FLOW_A, FLOW_B, ONB_ID, FakeRunner, with_metrics, with_step
from verdict_agent.adapty_cli import AdaptyCLI, WrongAccount
from verdict_agent.calibration import Calibration
import verdict_agent.live as live
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
        assert by["none"] == row["users"] - (row["trials"] - row["trials_paid"]) - row["unique_paid_subscribers"]
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



def _arm_sums(arm, row):
    by = {s: sum(g.n for g in arm.groups if g.status == s) for s in ("trial", "active", "none")}
    assert by["trial"] == row["trials"] - row["trials_paid"]
    assert by["active"] == row["unique_paid_subscribers"]
    assert by["none"] == row["users"] - by["trial"] - by["active"]
    return {(g.status, g.product): g.n for g in arm.groups}


CONVERTED_B = with_step("funnel_arm_2.json", {
    "Premium Weekly (3-day trial)": {"1 period": 10}, "lumen_weekly": {"1 period": 5},
})


def test_converted_trials_land_in_active_groups(caplog):
    metrics = with_metrics(B={"trials_paid": 15, "unique_paid_subscribers": 50})
    runner = FakeRunner(metrics=metrics, funnels={FLOW_B: CONVERTED_B})
    with caplog.at_level(logging.WARNING, logger="verdict_agent.live"):
        t = live_test(fake_cli(runner), APP, ONB_ID, TODAY)
    assert caplog.records == []
    b = next(a for a in t.arms if a.title == "B")
    row = next(r for r in metrics["data"]["metrics"] if r["title"] == "B")
    groups = _arm_sums(b, row)
    assert groups == {("trial", "weekly"): 56, ("active", "weekly"): 15, ("active", "annual"): 35, ("none", "-"): 179}


def test_funnel_conversions_scaled_to_metrics_trials_paid(caplog):
    metrics = with_metrics(B={"trials_paid": 12, "unique_paid_subscribers": 47})
    runner = FakeRunner(metrics=metrics, funnels={FLOW_B: CONVERTED_B})
    with caplog.at_level(logging.WARNING, logger="verdict_agent.live"):
        t = live_test(fake_cli(runner), APP, ONB_ID, TODAY)
    assert any("trials_paid" in r.getMessage() for r in caplog.records)
    b = next(a for a in t.arms if a.title == "B")
    row = next(r for r in metrics["data"]["metrics"] if r["title"] == "B")
    assert _arm_sums(b, row)[("active", "weekly")] == 12


def test_metrics_conversions_without_funnel_steps_spread_by_trials(caplog):
    metrics = with_metrics(A={"trials_paid": 10, "unique_paid_subscribers": 10})
    t = live_test(fake_cli(FakeRunner(metrics=metrics)), APP, ONB_ID, TODAY)
    a = next(x for x in t.arms if x.title == "A")
    row = next(r for r in metrics["data"]["metrics"] if r["title"] == "A")
    groups = _arm_sums(a, row)
    assert groups[("active", "annual_trial")] == 7 and groups[("active", "weekly")] == 3


def test_run_live_excludes_offline_test_with_live_title(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"LUMEN_APP_ID={APP}\nADAPTY_EXPECTED_COMPANY={COMPANY}\nVERDICT_DATASET=/synthetic\n")
    seen = []
    real = live.build_offline

    def spy(users, exclude_test, horizon):
        seen.append(exclude_test)
        return real(users, exclude_test, horizon)

    users = {
        "u1": {"test": "Onboarding: annual trial vs weekly first", "arm": "x", "ev": [(1.0, 100.0)], "subs": [(1.0, 9.0, "weekly", False)]},
        "u2": {"test": "", "arm": "", "ev": [], "subs": []},
    }
    monkeypatch.setattr(live, "build_offline", spy)
    monkeypatch.setattr(live, "_cached_users", lambda path, horizon: (users, {}))
    out = run_live(ONB_ID, TODAY, cli=fake_cli(), env_path=env)
    assert seen == ["Onboarding: annual trial vs weekly first"]
    assert out["calibration_source"] == "offline_calibration"
    assert out["arms"][0]["revenue_expected_renewals"] == 0

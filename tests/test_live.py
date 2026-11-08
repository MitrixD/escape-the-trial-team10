import json
import logging
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from verdict_agent.adapty_cli import AdaptyCLI, CliError, replay_runner
from verdict_agent.calibration import build_from_adapty, periods_from_catalog, product_map_from_catalog
from verdict_agent.live import expire_trials, live_calibration, live_test, read_products, read_test
from verdict_agent.model import DEFAULT_TRIAL_DAYS, Arm, Group, TestData, VerdictError

LIVE = Path(__file__).parent / "fixtures" / "live"
ONBOARDING = LIVE / "995b124f-9075-440d-83bb-20dbdf7d7fbb"
TODAY = date(2026, 11, 7)
APP = "app-1"


def load(bundle, name):
    return json.loads((bundle / name).read_text())


class Spy:
    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd[1:])
        return self.inner(cmd, **kw)


def replay(bundle):
    spy = Spy(replay_runner(bundle))
    return AdaptyCLI(runner=spy, min_interval=0), spy


def catalog_ids(bundle):
    return {p["title"]: p["id"] for p in load(bundle, "products_list.json")["data"]}


def metrics_rows(bundle):
    return {r["title"]: r for r in load(bundle, "ab-tests_metrics_total.json")["data"]["metrics"]}


def by(arm, status):
    out = {}
    for g in arm.groups:
        if g.status == status:
            prev = out.get(g.product)
            out[g.product] = g if prev is None else replace(prev, n=prev.n + g.n)
    return out


def ages(arm, status, product):
    return {g.age_days: g.n for g in arm.groups if g.status == status and g.product == product}


@pytest.mark.parametrize("bundle", [ONBOARDING], ids=["onboarding"])
def test_arm_fields_follow_metrics_and_test(bundle):
    cli, _ = replay(bundle)
    test = live_test(cli, APP, bundle.name, TODAY)
    got = load(bundle, "ab-tests_get.json")
    rows = metrics_rows(bundle)
    assert test.ab_test_id == got["ab_test_id"]
    assert test.title == got["title"]
    assert test.placement_id == got["placement"]["placement_id"]
    assert test.started_on == date(2026, 11, 7)
    assert test.as_of == TODAY
    assert [a.title for a in test.arms] == [f["title"] for f in got["flows"]]
    for arm in test.arms:
        row = rows[arm.title]
        assert arm.users == row["users"]
        assert arm.purchases == row["purchases"]
        assert arm.trials == row["trials"]
        assert arm.paid_users == row["unique_paid_subscribers"]
        assert arm.revenue_received == pytest.approx(row["revenue"])
        assert all(g.age_days == 0.5 for g in arm.groups)
    assert test.users_per_day == sum(r["users"] for r in rows.values())


def test_onboarding_users_and_trials():
    cli, _ = replay(ONBOARDING)
    test = live_test(cli, APP, ONBOARDING.name, TODAY)
    assert sorted(a.users for a in test.arms) == [254, 285]
    assert sorted(a.trials for a in test.arms) == [66, 71]
    for arm in test.arms:
        assert sum(g.n for g in arm.groups if g.status == "trial") == arm.trials
        assert sum(g.n for g in arm.groups if g.status == "active") == arm.paid_users


def test_onboarding_store_keys_merge_through_catalog():
    cli, _ = replay(ONBOARDING)
    test = live_test(cli, APP, ONBOARDING.name, TODAY)
    ids = catalog_ids(ONBOARDING)
    a, b = test.arms
    weekly, annual_trial, annual = ids["Premium Weekly (3-day trial)"], ids["Premium Annual (7-day trial)"], ids["Premium Annual"]
    assert {p: g.n for p, g in by(a, "trial").items()} == {annual_trial: 29 + 18, weekly: 12 + 7}
    assert by(a, "active") == {}
    assert {p: g.n for p, g in by(b, "trial").items()} == {weekly: 45 + 26}
    active_b = by(b, "active")
    assert {p: g.n for p, g in active_b.items()} == {annual: 16 + 19}
    assert active_b[annual].received == pytest.approx(1527.9004004819967 / 35)
    assert by(b, "none")["-"].n == 285 - 71 - 35
    assert all(g.received == 0 for g in b.groups if g.status in ("trial", "none"))
    products = {g.product for arm in test.arms for g in arm.groups if g.status != "none"}
    assert products <= set(ids.values())


@pytest.mark.parametrize("bundle", [ONBOARDING], ids=["onboarding"])
def test_groups_reproduce_test_metrics(bundle):
    cli, _ = replay(bundle)
    test = live_test(cli, APP, bundle.name, TODAY)
    rows = metrics_rows(bundle)
    for arm in test.arms:
        row = rows[arm.title]
        assert sum(g.n * g.received for g in arm.groups) == pytest.approx(arm.revenue_received)
        trial_starts = sum(g.n for g in arm.groups if g.status == "trial") + row["trials_paid"]
        assert trial_starts == arm.trials == row["trials"]
        assert sum(g.n for g in arm.groups if g.status == "active") == arm.paid_users


def test_live_test_reads_five_commands_and_reuses_catalog():
    cli, spy = replay(ONBOARDING)
    live_test(cli, APP, ONBOARDING.name, TODAY)
    assert [c[:2] for c in spy.calls] == [
        ["ab-tests", "get"], ["ab-tests", "metrics"], ["products", "list"],
        ["analytics", "funnel"], ["analytics", "funnel"],
    ]
    funnel = spy.calls[3]
    assert "placement_id=a0876118-9ad3-4d77-adce-c89f9ee874aa" in funnel
    assert funnel[funnel.index("--group-by") + 1] == "store_product_id"
    assert funnel[funnel.index("--date-from") + 1] == "2026-11-07"
    assert funnel[funnel.index("--date-to") + 1] == "2026-11-07"

    cli, spy = replay(ONBOARDING)
    products = read_products(cli, APP)
    live_test(cli, APP, ONBOARDING.name, TODAY, products=products)
    cal = live_calibration(cli, APP, products, 60, date(2026, 11, 7))
    assert len(spy.calls) == 7
    assert [c[:2] for c in spy.calls].count(["products", "list"]) == 1
    assert cal.source == "product"


class FakeCli:
    def __init__(self, test, metrics, funnels, products):
        self.responses = {"get": test, "metrics": metrics, "list": products}
        self.funnels = funnels
        self.calls = []

    def run(self, args):
        self.calls.append(args)
        if args[:2] == ["analytics", "funnel"]:
            arm_filter = next(a for a in args if a.startswith(("flow_id=", "paywall_id=")))
            return self.funnels[arm_filter]
        return self.responses[args[1]]


CATALOG = {"data": [
    {"id": "u-week", "title": "Weekly Plan", "vendor_products": {
        "app_store": {"product_id": "com.x.week"}, "play_store": {"product_id": "x_week"}}},
    {"id": "u-year", "title": "Yearly Plan", "vendor_products": {
        "app_store": {"product_id": "com.x.year"}, "play_store": {"product_id": "x_year"}}},
]}


def seg(key, steps):
    return {"key": key, "title": key, "is_total": False,
            "values": [{"x": i, "title": t, "value": v} for i, (t, v) in enumerate(steps)]}


def fake(segments, row, arm_key="flows", arm_id="flow_id"):
    test = {"ab_test_id": "t1", "title": "Synthetic", "placement": {"placement_id": "pl-1"},
            "started_at": "2026-11-01T10:00:00Z", arm_key: [{arm_id: "f1", "title": "A"}]}
    metrics = {"data": {"metrics": [{arm_id: "f1", "title": "A", **row}]}}
    return FakeCli(test, metrics, {f"{arm_id}=f1": {"data": {"segments": segments}}}, CATALOG)


ROW = {"users": 200, "purchases": 5, "trials": 45, "trials_paid": 15, "unique_paid_subscribers": 20, "revenue": 400.0}


def test_one_period_conversions_go_to_active():
    cli = fake([seg("Weekly Plan", [("Install", 900), ("Paywall displayed", 200), ("Trial", 45), ("1 period", 15)]),
                seg("x_year", [("Install", 900), ("-1 period", 0), ("0 period", 0), ("Paid", 5)])], ROW)
    arm = live_test(cli, APP, "t1", date(2026, 11, 6)).arms[0]
    assert by(arm, "trial")["u-week"].n == 30
    assert by(arm, "active")["u-week"].n == 15
    assert by(arm, "active")["u-year"].n == 5
    assert by(arm, "active")["u-week"].received == pytest.approx(400.0 / 20)
    assert by(arm, "none")["-"].n == 200 - 30 - 20
    assert ages(arm, "active", "u-week") == {4.5: 15}
    assert ages(arm, "trial", "u-week") == {d + 0.5: 6 for d in range(5)}
    assert [g.age_days for g in arm.groups if g.status == "none"] == [2.5]


def test_converted_reconciled_to_metrics_trials_paid():
    cli = fake([seg("Weekly Plan", [("Trial", 30), ("1 period", 1)]),
                seg("com.x.year", [("Trial", 3), ("Paid", 0)])],
               {**ROW, "trials": 33, "trials_paid": 10, "purchases": 0, "unique_paid_subscribers": 10})
    arm = live_test(cli, APP, "t1", TODAY).arms[0]
    active = {p: g.n for p, g in by(arm, "active").items()}
    trial = {p: g.n for p, g in by(arm, "trial").items()}
    assert sum(active.values()) == 10
    assert active.get("u-year", 0) <= 3
    assert {p: trial.get(p, 0) + active.get(p, 0) for p in ("u-week", "u-year")} == {"u-week": 30, "u-year": 3}


def test_uuid_and_store_keys_merge_and_unknown_label_passes_through(caplog):
    cli = fake([seg("u-week", [("Trial", 2)]), seg("play_store:x_week", [("Trial", 3)]),
                seg("com.x.week", [("Trial", 4)]), seg("mystery_sku", [("Trial", 1)])],
               {**ROW, "trials": 10, "trials_paid": 0, "purchases": 0, "unique_paid_subscribers": 0})
    with caplog.at_level(logging.WARNING, logger="verdict_agent.live"):
        arm = live_test(cli, APP, "t1", TODAY).arms[0]
    assert {p: g.n for p, g in by(arm, "trial").items()} == {"u-week": 9, "mystery_sku": 1}
    assert "mystery_sku" in caplog.text


def test_none_group_clamped(caplog):
    cli = fake([seg("Weekly Plan", [("Trial", 50)])],
               {**ROW, "users": 40, "trials": 50, "trials_paid": 0, "purchases": 0, "unique_paid_subscribers": 0})
    with caplog.at_level(logging.WARNING, logger="verdict_agent.live"):
        arm = live_test(cli, APP, "t1", TODAY).arms[0]
    assert by(arm, "none") == {}
    assert "clamped" in caplog.text


def test_paywall_test_filters_funnel_by_paywall():
    cli = fake([seg("Weekly Plan", [("Trial", 45), ("1 period", 15)])], ROW, arm_key="paywalls", arm_id="paywall_id")
    test = live_test(cli, APP, "t1", TODAY)
    funnel = next(c for c in cli.calls if c[:2] == ["analytics", "funnel"])
    assert "paywall_id=f1" in funnel and "placement_id=pl-1" in funnel
    assert test.arms[0].users == 200


def make_test(groups, age):
    return TestData("t", "T", None, date(2026, 11, 1), date(2026, 11, 1), 1.0,
                    [Arm("A", [Group(s, p, age, n, r) for s, p, n, r in groups], 0, 0, 0, 0.0)])


def test_expire_trials_moves_old_trials_to_ended():
    test = make_test([("trial", "weekly", 10, 0.0), ("trial", "annual", 4, 0.0),
                      ("active", "weekly", 3, 9.0), ("none", "-", 20, 0.0)], age=5)
    out = expire_trials(test, {"weekly": 3, "annual": 7})
    groups = {(g.status, g.product): g for g in out.arms[0].groups}
    assert groups[("ended", "weekly")].n == 10 and groups[("ended", "weekly")].received == 0
    assert ("trial", "weekly") not in groups
    assert groups[("trial", "annual")].n == 4
    assert groups[("active", "weekly")].n == 3
    assert [g.status for g in test.arms[0].groups] == ["trial", "trial", "active", "none"]


def test_expire_trials_default_length_for_unknown_product():
    young = expire_trials(make_test([("trial", "new", 5, 0.0)], age=DEFAULT_TRIAL_DAYS), {})
    old = expire_trials(make_test([("trial", "new", 5, 0.0)], age=DEFAULT_TRIAL_DAYS + 1), {})
    assert young.arms[0].groups[0].status == "trial"
    assert old.arms[0].groups[0].status == "ended"


@pytest.mark.parametrize("bundle", [ONBOARDING], ids=["onboarding"])
def test_live_calibration_from_recorded_analytics(bundle):
    cli, spy = replay(bundle)
    cal = live_calibration(cli, APP, None, 60, date(2026, 11, 7))
    products = load(bundle, "products_list.json")
    expected = build_from_adapty(load(bundle, "analytics_conversion_trial-paid.json"),
                                 load(bundle, "analytics_ltv.json"), 60, product_map_from_catalog(products),
                                 periods_from_catalog(products))
    assert cal == expected
    assert set(cal.periods.values()) <= {"weekly", "monthly", "annual", "lifetime"}
    assert cal.source == "product"
    assert set(cal.renewal_value) <= {p["id"] for p in products["data"]}
    assert [c[:2] for c in spy.calls] == [
        ["products", "list"], ["analytics", "conversion"], ["analytics", "ltv"]]
    for call in spy.calls[1:]:
        assert call[call.index("--date-from") + 1] == "2026-05-11"
        assert call[call.index("--date-to") + 1] == "2026-11-06"
        assert call[call.index("--app") + 1] == APP
    conversion, ltv = spy.calls[1:]
    assert conversion[conversion.index("--group-by") + 1] == "store_product_id"
    assert ltv[ltv.index("--group-by") + 1] == "store_product_id"


def test_one_period_step_decides_which_product_converted():
    cli = fake([seg("Weekly Plan", [("Trial", 20), ("1 period", 10)]), seg("x_year", [("Trial", 20), ("1 period", 0)])],
               {**ROW, "trials": 40, "trials_paid": 10, "purchases": 0, "unique_paid_subscribers": 10})
    arm = live_test(cli, APP, "t1", TODAY).arms[0]
    assert {p: g.n for p, g in by(arm, "active").items()} == {"u-week": 10}
    assert {p: g.n for p, g in by(arm, "trial").items()} == {"u-week": 10, "u-year": 20}


def test_funnel_counts_scaled_to_metrics_by_largest_remainder(caplog):
    cli = fake([seg("Weekly Plan", [("Trial", 6)]), seg("x_year", [("Trial", 3)]),
                seg("com.x.week", [("Paid", 4)]), seg("Yearly Plan", [("Paid", 2)])],
               {**ROW, "trials": 6, "trials_paid": 0, "purchases": 3, "unique_paid_subscribers": 3, "revenue": 90.0})
    with caplog.at_level(logging.WARNING, logger="verdict_agent.live"):
        arm = live_test(cli, APP, "t1", TODAY).arms[0]
    assert {p: g.n for p, g in by(arm, "trial").items()} == {"u-week": 4, "u-year": 2}
    assert {p: g.n for p, g in by(arm, "active").items()} == {"u-week": 2, "u-year": 1}
    assert sum(g.n * g.received for g in arm.groups) == pytest.approx(90.0)
    assert "scaled per product" in caplog.text


def test_lagging_funnel_scaled_up_to_metrics(caplog):
    cli = fake([seg("Weekly Plan", [("Install", 30), ("Paid", 1)])],
               {**ROW, "users": 40, "trials": 0, "trials_paid": 0, "purchases": 3, "unique_paid_subscribers": 3,
                "revenue": 149.97})
    with caplog.at_level(logging.WARNING, logger="verdict_agent.live"):
        arm = live_test(cli, APP, "t1", TODAY).arms[0]
    assert by(arm, "trial") == {}
    assert {p: g.n for p, g in by(arm, "active").items()} == {"u-week": 3}
    assert by(arm, "active")["u-week"].received == pytest.approx(49.99)
    assert arm.users == 40
    assert "scaled per product" in caplog.text


def test_metrics_without_row_for_arm_raise_clear_error():
    cli = fake([], ROW)
    cli.responses["metrics"] = {"data": {"metrics": []}}
    with pytest.raises(VerdictError, match="metrics have no row for arm A"):
        live_test(cli, APP, "t1", TODAY)


def test_metrics_row_is_never_matched_by_position():
    cli = fake([], ROW)
    cli.responses["metrics"] = {"data": {"metrics": [{"flow_id": "other", "variation_id": "v-other", "title": "B", **ROW}]}}
    with pytest.raises(VerdictError, match="metrics have no row for arm A"):
        live_test(cli, APP, "t1", TODAY)


def test_unknown_test_error_names_the_id():
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "404 not found")

    with pytest.raises(CliError) as err:
        read_test(AdaptyCLI(runner=runner, min_interval=0), APP, "missing-test-9")
    assert err.value.public == "cannot read A/B test missing-test-9: adapty exited with code 1"
    assert APP not in err.value.public


def test_product_with_unknown_trial_length_keeps_its_trials_for_seven_days():
    conversion = {"data": {"value_from": 10, "value_to": 5, "segments": [
        {"key": "u-week", "value_from": 10, "value_to": 5}]}}
    ltv = {"data": {"segments": [
        {"key": "u-week", "cohort_size": 5, "values": [{"x": 0, "value": 0}, {"x": 3, "value": 5}]},
        {"key": "u-year", "cohort_size": 5, "values": [{"x": 0, "value": 0}, {"x": 3, "value": 40}]}]}}
    cal = build_from_adapty(conversion, ltv, 60, product_map_from_catalog(CATALOG))
    assert cal.trial_days["u-year"] == 0
    test = expire_trials(make_test([("trial", "u-year", 4, 0.0), ("trial", "u-week", 4, 0.0)], age=1), cal.trial_days)
    assert {g.product: g.status for g in test.arms[0].groups} == {"u-year": "trial", "u-week": "trial"}
    old = expire_trials(make_test([("trial", "u-year", 4, 0.0)], age=8), cal.trial_days)
    assert [g.status for g in old.arms[0].groups] == ["ended"]


def test_active_users_spread_over_test_period():
    cli = fake([seg("Weekly Plan", [("Trial", 0), ("Paid", 0)]), seg("x_year", [("Paid", 8)])],
               {**ROW, "trials": 0, "trials_paid": 0, "purchases": 8, "unique_paid_subscribers": 8, "revenue": 80.0})
    arm = live_test(cli, APP, "t1", date(2026, 11, 5)).arms[0]
    assert ages(arm, "active", "u-year") == {0.5: 2, 1.5: 2, 2.5: 2, 3.5: 2}
    assert all(g.received == pytest.approx(10.0) for g in arm.groups if g.status == "active")


def test_active_counts_per_age_by_largest_remainder_reproduce_metrics():
    cli = fake([seg("x_year", [("Paid", 7)])],
               {**ROW, "trials": 0, "trials_paid": 0, "purchases": 7, "unique_paid_subscribers": 7, "revenue": 70.0})
    arm = live_test(cli, APP, "t1", date(2026, 11, 11)).arms[0]
    spread = ages(arm, "active", "u-year")
    assert sum(spread.values()) == 7
    assert set(spread.values()) == {1}
    assert set(spread) <= {d + 0.5 for d in range(10)}
    assert sum(g.n * g.received for g in arm.groups) == pytest.approx(70.0)


def test_share_of_unconverted_trials_still_in_trial():
    cli = fake([seg("Weekly Plan", [("Trial", 100), ("1 period", 0)])],
               {**ROW, "trials": 100, "trials_paid": 0, "purchases": 0, "unique_paid_subscribers": 0, "revenue": 0.0})
    arm = live_test(cli, APP, "t1", date(2026, 11, 11), trial_days={"u-week": 3}).arms[0]
    assert ages(arm, "trial", "u-week") == {0.5: 10, 1.5: 10, 2.5: 10}
    assert by(arm, "ended")["u-week"].n == 70
    assert [g.n for g in arm.groups if g.status == "none"] == [100]


def test_trials_younger_than_the_test_stay_in_trial_unknown_length_defaults():
    cli = fake([seg("Weekly Plan", [("Trial", 9), ("1 period", 0)])],
               {**ROW, "trials": 9, "trials_paid": 0, "purchases": 0, "unique_paid_subscribers": 0, "revenue": 0.0})
    arm = live_test(cli, APP, "t1", date(2026, 11, 4)).arms[0]
    assert ages(arm, "trial", "u-week") == {0.5: 3, 1.5: 3, 2.5: 3}
    assert by(arm, "ended") == {}


def test_expire_trials_is_a_no_op_on_live_test_output():
    cli = fake([seg("Weekly Plan", [("Trial", 45), ("1 period", 15)]), seg("x_year", [("Paid", 5)])], ROW)
    test = live_test(cli, APP, "t1", date(2026, 11, 21), trial_days={"u-week": 3})
    assert expire_trials(test, {"u-week": 3}) == test


def test_live_test_reuses_a_read_test_without_another_get():
    cli = fake([seg("Weekly Plan", [("Trial", 45), ("1 period", 15)])], ROW)
    got = read_test(cli, APP, "t1")
    live_test(cli, APP, "t1", TODAY, products=CATALOG, test=got)
    assert [c[:2] for c in cli.calls].count(["ab-tests", "get"]) == 1


# --- hardening (change harden-verdict-agent, groups 2 and 4.3) ---

def test_draft_test_is_rejected():
    cli = fake([seg("Weekly Plan", [("Trial", 0)])], ROW)
    cli.responses["get"] = {**cli.responses["get"], "started_at": None}
    with pytest.raises(VerdictError, match="has not started"):
        live_test(cli, APP, "t1", date(2026, 11, 6))


def test_stopped_test_uses_its_running_period():
    cli = fake([seg("x_year", [("Paid", 6)])],
               {**ROW, "users": 60, "trials": 0, "trials_paid": 0, "purchases": 6, "unique_paid_subscribers": 6,
                "revenue": 60.0})
    cli.responses["get"] = {**cli.responses["get"], "stopped_at": "2026-11-04T10:00:00Z"}
    test = live_test(cli, APP, "t1", date(2026, 12, 1))
    assert test.users_per_day == pytest.approx(60 / 3)
    assert min(g.age_days for g in test.arms[0].groups) >= 27
    assert test.stopped and test.running_days == 3


def test_pending_share_counts_all_trial_starts():
    cli = fake([seg("Weekly Plan", [("Trial", 100), ("1 period", 50)])],
               {**ROW, "trials": 100, "trials_paid": 50, "purchases": 0, "unique_paid_subscribers": 50, "revenue": 500.0})
    arm = live_test(cli, APP, "t1", date(2026, 11, 11), trial_days={"u-week": 3}).arms[0]
    assert sum(ages(arm, "trial", "u-week").values()) == 30
    assert by(arm, "ended")["u-week"].n == 20


def test_converted_trial_users_are_at_least_as_old_as_the_trial():
    cli = fake([seg("Weekly Plan", [("Trial", 40), ("1 period", 20)])],
               {**ROW, "trials": 40, "trials_paid": 20, "purchases": 0, "unique_paid_subscribers": 20, "revenue": 200.0})
    arm = live_test(cli, APP, "t1", date(2026, 11, 11), trial_days={"u-week": 7}).arms[0]
    assert min(ages(arm, "active", "u-week")) >= 7


def test_unknown_trial_length_with_trials_in_the_funnel_uses_seven_days(caplog):
    cli = fake([seg("Weekly Plan", [("Trial", 20), ("1 period", 0)])],
               {**ROW, "trials": 20, "trials_paid": 0, "purchases": 0, "unique_paid_subscribers": 0, "revenue": 0.0})
    with caplog.at_level(logging.WARNING):
        test = live_test(cli, APP, "t1", date(2026, 11, 11), trial_days={"u-week": 0})
    test = expire_trials(test, {"u-week": 0})
    assert sum(ages(test.arms[0], "trial", "u-week").values()) == 14
    assert "u-week" in caplog.text and "7" in caplog.text

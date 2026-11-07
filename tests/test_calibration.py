import json
from pathlib import Path

import pytest

from verdict_agent.calibration import build_from_adapty, load, product_map_from_catalog, save

LIVE = Path(__file__).parent / "fixtures" / "live" / "995b124f-9075-440d-83bb-20dbdf7d7fbb"
WEEKLY = "db187773-c682-49f5-9be1-648178c284c1"
ANNUAL_TRIAL = "0c94bfa2-0b08-4cdd-a27e-2f2327e315dd"
ANNUAL = "bd8ca735-45d0-4945-aefc-cd9d330938d2"
MONTHLY = "9bf9b354-5e29-40f0-96d9-072c0ee54700"
LIFETIME = "ff76ad13-624f-4771-a9bc-313c27b2239a"
PRO_ANNUAL = "69cec9be-a51c-44f9-b80a-33737947277e"


def read(name):
    return json.loads((LIVE / name).read_text())


@pytest.fixture(scope="module")
def recorded():
    return {
        "conversion": read("analytics_conversion_trial-paid.json"),
        "cohort": read("analytics_cohort.json"),
        "ltv": read("analytics_ltv.json"),
        "product_map": product_map_from_catalog(read("products_list.json")),
    }


@pytest.fixture(scope="module")
def cal(recorded):
    return build_from_adapty(horizon=60, **recorded)


def test_product_map_from_catalog(recorded):
    m = recorded["product_map"]
    assert m[WEEKLY] == WEEKLY
    assert m["play_store:lumen_weekly"] == WEEKLY
    assert m["app_store:lumen.weekly"] == WEEKLY
    assert m["play_store:lumen_annual_trial"] == ANNUAL_TRIAL
    assert len(m) == 18
    assert set(m.values()) == {WEEKLY, ANNUAL_TRIAL, ANNUAL, MONTHLY, LIFETIME, PRO_ANNUAL}


def test_product_map_skips_missing_store_products():
    catalog = {"data": [{"id": "u1", "vendor_products": {"app_store": {"product_id": "a"}, "play_store": None}}]}
    assert product_map_from_catalog(catalog) == {"u1": "u1", "app_store:a": "u1"}


def test_trial_to_paid_merges_uuid_and_store_keys(cal):
    assert cal.trial_to_paid[WEEKLY] == pytest.approx((169 + 91) / (353 + 188))
    assert cal.trial_to_paid[ANNUAL_TRIAL] == pytest.approx((55 + 32) / (157 + 89))
    assert set(cal.trial_to_paid) == {WEEKLY, ANNUAL_TRIAL}
    assert "play_store:lumen_weekly" not in cal.trial_to_paid
    assert cal.app_trial_to_paid == pytest.approx(347 / 787)


def test_curves_merge_keys_weighted_by_cohort_size(cal):
    weekly = cal.renewal_value[WEEKLY]
    assert len(weekly) == 61
    assert weekly[0] == 0
    assert weekly[3] == pytest.approx((7.49 * 152 + 6.79 * 83) / 235)
    at31 = (25.34 * 152 + 23.71 * 83) / 235
    at61 = (33.03 * 152 + 30.96 * 83) / 235
    assert weekly[31] == pytest.approx(at31)
    assert weekly[60] == pytest.approx(at31 + (at61 - at31) * 29 / 30)
    assert cal.renewal_value[PRO_ANNUAL][10] == pytest.approx((82.99 * 59 + 77.58 * 35) / 94)
    assert cal.renewal_value[LIFETIME] == [pytest.approx(99.37)] * 61
    assert "play_store:lumen_weekly" not in cal.renewal_value
    assert set(cal.renewal_value) == {WEEKLY, ANNUAL_TRIAL, ANNUAL, MONTHLY, LIFETIME, PRO_ANNUAL}


def test_app_curve_from_total_row(cal):
    assert len(cal.app_renewal_value) == 61
    assert cal.app_renewal_value[0] == pytest.approx(32.99)
    assert cal.app_renewal_value[5] == pytest.approx(34.93 + (39.43 - 34.93) * 2 / 4)


def test_curve_flat_after_last_point(recorded):
    long = build_from_adapty(horizon=400, **recorded)
    assert len(long.renewal_value[WEEKLY]) == 401
    assert long.renewal_value[WEEKLY][183] == long.renewal_value[WEEKLY][400]
    assert long.renewal_value[WEEKLY][400] == pytest.approx((36.13 * 152 + 33.21 * 83) / 235)


def test_trial_days_from_curve(cal):
    assert cal.trial_days[WEEKLY] == 3
    assert cal.trial_days[ANNUAL_TRIAL] == 7
    assert cal.trial_days[ANNUAL] == 0
    assert cal.trial_days[MONTHLY] == 0
    assert cal.trial_days[LIFETIME] == 0


def test_source_product_and_unknown_product_is_app(cal):
    assert cal.source == "product"
    assert cal.source_for(WEEKLY) == "product"
    assert cal.source_for("not-in-history") == "app"


def test_expected_on_recorded_calibration(cal):
    gain = cal.renewal_value[WEEKLY][60] - cal.renewal_value[WEEKLY][0]
    assert cal.expected("trial", WEEKLY, 0, 60) == pytest.approx(gain)
    assert cal.expected("active", WEEKLY, 0, 60) == pytest.approx(gain / cal.trial_to_paid[WEEKLY])
    assert cal.expected("active", LIFETIME, 0, 60) == pytest.approx(0)


def test_empty_ltv_reports_none(recorded):
    for ltv in (None, {}, {"data": {"value": 0, "segments": []}}):
        c = build_from_adapty(recorded["conversion"], recorded["cohort"], ltv, 60, recorded["product_map"])
        assert c.source == "none"
        assert c.renewal_value == {}
        assert c.app_renewal_value is None
        assert c.source_for(WEEKLY) == "none"
        assert c.expected("trial", WEEKLY, 0, 60) == 0


def test_empty_responses_report_none():
    c = build_from_adapty({}, {}, None, 60, {})
    assert c.source == "none"
    assert c.trial_to_paid == {}
    assert c.app_trial_to_paid is None


def test_app_only_curve_reports_app():
    ltv = {"data": {"segments": [
        {"key": None, "is_total": True, "cohort_size": 10, "values": [{"x": 0, "value": 1.0}, {"x": 10, "value": 11.0}]},
    ]}}
    c = build_from_adapty({"data": {"value_from": 0, "value_to": 0, "segments": []}}, {}, ltv, 5, {})
    assert c.source == "app"
    assert c.app_renewal_value == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert c.app_trial_to_paid is None


def test_unknown_keys_map_to_themselves_and_null_points_skipped():
    ltv = {"data": {"segments": [
        {"key": "play_store:x", "is_total": False, "cohort_size": 0,
         "values": [{"x": 0, "value": 0}, {"x": 2, "value": 4.0}, {"x": 366, "value": None}]},
    ]}}
    conv = {"data": {"value_from": 4, "value_to": 1, "segments": [
        {"key": "play_store:x", "is_total": False, "value_from": 4, "value_to": 1},
    ]}}
    c = build_from_adapty(conv, {}, ltv, 3, {})
    assert c.renewal_value["play_store:x"] == [0.0, 2.0, 4.0, 4.0]
    assert c.trial_to_paid["play_store:x"] == 0.25
    assert c.trial_days["play_store:x"] == 2


def test_save_load_roundtrip(cal, tmp_path):
    path = tmp_path / "cal.json"
    save(cal, path)
    assert load(path) == cal

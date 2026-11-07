import copy

import pytest

from tests.helpers import build_checked_verdict, make_arm, make_cal, make_test, step_curve
from tests.schema_check import errors, load_schema


def two_arms(gain, users, payers_a, payers_b, source="product"):
    cal = make_cal({"p": step_curve(gain)}, source=source)
    return make_test([make_arm("A", users, payers_a), make_arm("B", users, payers_b)]), cal


@pytest.fixture
def confirmed():
    return build_checked_verdict(*two_arms(15.0, 200, 49, 66))


def test_schema_is_a_json_schema_document():
    schema = load_schema()
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "ab_test_id", "verdict", "reason", "leader", "p2bb_expected", "p2bb_raw",
        "maturity", "horizon_days", "come_back_on", "arms", "calibration_source", "expected_gap_per_user",
        "money", "next_action", "next_action_basis",
    }
    assert set(schema["properties"]["arms"]["items"]["required"]) == {
        "title", "users", "revenue_received", "revenue_expected_trials", "revenue_expected_renewals",
        "revenue_expected_total",
    }


@pytest.mark.parametrize("source", ["product", "app"])
def test_reason_only_when_undecided(source):
    decided = [
        build_checked_verdict(*two_arms(15.0, 200, 49, 66, source)),
        build_checked_verdict(*two_arms(10 / 0.9 - 10, 20000, 10000, 10000, source)),
    ]
    assert [d["verdict"] for d in decided] == ["confirmed", "tie"]
    for d in decided:
        assert d["reason"] is None
        assert d["calibration_source"] in ("product", "app", "none")


def test_undecided_verdicts_validate():
    test, cal = two_arms(10.0, 200, 67, 72)
    assert build_checked_verdict(test, cal)["verdict"] == "keep_running"
    assert build_checked_verdict(test, make_cal({}, source="none"))["reason"] == "no_calibration"


def mutate(out, change):
    bad = copy.deepcopy(out)
    change(bad)
    return errors(bad, load_schema())


@pytest.mark.parametrize("change", [
    lambda o: o.pop("leader"),
    lambda o: o.update(note="free text"),
    lambda o: o["arms"][0].update(warnings=[]),
    lambda o: o["arms"][0].pop("users"),
    lambda o: o.update(verdict="early"),
    lambda o: o.update(reason="min_events"),
    lambda o: o.update(come_back_on="2026-12-14"),
    lambda o: o.update(horizon_days=True),
    lambda o: o.update(horizon_days=0),
    lambda o: o.update(p2bb_expected=1.5),
    lambda o: o.update(calibration_source="test"),
    lambda o: o.update(arms=o["arms"][:1]),
    lambda o: o.update(verdict="keep_running", reason="min_events"),
    lambda o: o.update(verdict="keep_running", reason="pending_revenue", come_back_on="14 Dec"),
    lambda o: o.update(verdict="not_enough_data", reason="no_calibration", come_back_on="2026-12-14"),
    lambda o: o.update(verdict="not_enough_data", reason="min_events", next_action="come_back"),
    lambda o: o.update(next_action="come_back", next_action_basis="money"),
    lambda o: o.update(money=dict(o["money"], cost_until_come_back=12.0)),
    lambda o: o.pop("expected_gap_per_user"),
    lambda o: o.update(expected_gap_per_user=-0.5),
    lambda o: o["arms"][0].pop("revenue_expected_total"),
])
def test_checker_rejects_outputs_outside_the_contract(confirmed, change):
    assert mutate(confirmed, change)


def test_checker_accepts_a_produced_verdict(confirmed):
    assert errors(confirmed, load_schema()) == []


def test_min_events_may_carry_a_date_and_no_calibration_may_not(confirmed):
    ok = dict(confirmed, verdict="not_enough_data", reason="min_events", come_back_on="2026-12-14",
              money=None, next_action="come_back")
    assert errors(ok, load_schema()) == []
    assert errors(dict(ok, reason="no_calibration", come_back_on=None), load_schema()) == []

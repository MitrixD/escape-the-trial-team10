import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.helpers import AS_OF, STARTED_ON, closest_k, fake, make_test, payer_arm
from verdict_agent.calibration import Calibration
from verdict_agent.estimator import estimate, pseudo_values
from verdict_agent.model import Arm, Group
from verdict_agent.stats import p2bb
from verdict_agent.verdict import build_verdict, horizon_from_goal

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "verdict_agent" / "schema.json").read_text())
TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "integer": int, "number": (int, float), "null": type(None),
}


def v(fake_result, **kwargs):
    test, cal = fake_result
    return build_verdict(test, cal, **kwargs)


def check(value, schema, path="$"):
    types = schema.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        ok = any(
            isinstance(value, TYPES[t]) and not (t in ("integer", "number") and isinstance(value, bool))
            for t in types
        )
        assert ok, f"{path}: {value!r} is not {types}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} not in {schema['enum']}"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, f"{path}: missing {key}"
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            assert not extra, f"{path}: unexpected {extra}"
        for key, sub in props.items():
            if key in value:
                check(value[key], sub, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            check(item, schema["items"], f"{path}[{i}]")


def test_not_enough_data():
    out = v(fake(events=[12, 80]))
    assert out["verdict"] == "not_enough_data"
    assert out["next_step"]["type"] == "extend"


def test_not_enough_data_come_back_on():
    out = v(fake(events=[12, 80]))
    days = (date(*AS_OF) - date(*STARTED_ON)).days
    rate = 12 / days
    assert out["come_back_on"] == (date(*AS_OF) + timedelta(days=math.ceil(18 / rate))).isoformat()


def test_not_enough_data_without_events_has_no_date():
    out = v(fake(events=[0, 80]))
    assert out["verdict"] == "not_enough_data" and out["come_back_on"] is None


def test_zero_user_arm():
    out = v(fake(users=[0, 100]))
    assert out["verdict"] == "not_enough_data"
    assert out["arms"][0]["users"] == 0


def test_confident_before_maturity():
    out = v(fake(p2bb=0.97, maturity=0.4))
    assert out["p2bb_expected"] == pytest.approx(0.97, abs=0.01)
    assert out["maturity"] == pytest.approx(0.4, abs=0.01)
    assert out["verdict"] == "confirmed"
    assert out["leader"] == "B"
    assert out["come_back_on"] is None
    assert out["next_step"]["type"] == "stop_with_winner"


def test_immature_unsure():
    out = v(fake(p2bb=0.7, maturity=0.5))
    assert out["p2bb_expected"] == pytest.approx(0.7, abs=0.02)
    assert out["verdict"] == "early" and out["come_back_on"]
    assert out["next_step"]["type"] == "extend"


def test_mature_unsure():
    out = v(fake(p2bb=0.7, maturity=0.9))
    assert out["maturity"] == pytest.approx(0.9, abs=0.01)
    assert out["verdict"] == "tie" and out["next_step"]["type"] == "change_lever"
    assert "Do not repeat the same test" in out["next_step"]["reason"]
    assert out["come_back_on"] is None


def _trial_test(trial_days, goal="Find which onboarding offer maximises 60-day revenue per install"):
    cal = Calibration({}, {}, {"trial": 8.0, "active": 8.0, "none": 0.0}, "test")
    k_b = closest_k(0.7, 1000, 200, range(201, 400))
    arms = [
        payer_arm("A", 1000, 200, 2.0, 100, product="weekly_trial", status="trial"),
        payer_arm("B", 1000, k_b, 2.0, 100, product="annual_trial", status="trial"),
    ]
    return build_verdict(make_test(arms, goal=goal), cal, trial_days=trial_days)


def test_early_come_back_on_uses_slowest_trial():
    out = _trial_test({"weekly_trial": 3, "annual_trial": 14})
    assert out["verdict"] == "early"
    assert out["come_back_on"] == (date(*STARTED_ON) + timedelta(days=14 + 30)).isoformat()


def test_early_come_back_on_defaults_missing_trial_to_7_days():
    out = _trial_test({"weekly_trial": 3})
    assert out["come_back_on"] == (date(*STARTED_ON) + timedelta(days=7 + 30)).isoformat()


def test_early_come_back_on_capped_at_horizon():
    out = _trial_test({"weekly_trial": 3, "annual_trial": 14}, goal="Maximise 30-day revenue")
    assert out["horizon_days"] == 30
    assert out["come_back_on"] == (date(*STARTED_ON) + timedelta(days=30)).isoformat()


def test_early_without_trials_waits_one_renewal():
    out = v(fake(p2bb=0.7, maturity=0.5))
    assert out["come_back_on"] == (date(*STARTED_ON) + timedelta(days=30)).isoformat()


def test_horizon_from_goal():
    assert horizon_from_goal("Find which onboarding offer maximises 60-day revenue per install") == 60
    assert horizon_from_goal("Revenue over 90 days") == 90


def test_horizon_default():
    assert horizon_from_goal("lift annual share in North America") == 60
    assert horizon_from_goal("") == 60


def test_horizon_reported():
    test, cal = fake()
    test.goal = "Maximise 45-day revenue"
    out = build_verdict(test, cal)
    assert out["horizon_days"] == 45
    assert out["next_step"]["primary_metric"] == "net revenue per user, 45 days"


def test_equal_arms_no_money_at_stake():
    assert v(fake(equal=True))["money_at_stake_usd"] == 0


def test_money_at_stake_formula():
    test, cal = fake(p2bb=0.8, maturity=0.5)
    out = build_verdict(test, cal)
    a, b = (estimate(arm, cal).total for arm in test.arms)
    expected = abs(b - a) * test.users_per_day * 180 * (1 - p2bb(*(pseudo_values(arm, cal) for arm in test.arms)))
    assert out["money_at_stake_usd"] == round(expected, 2)
    assert out["money_at_stake_usd"] > 0


def test_three_arms_leader_vs_best_other():
    cal = Calibration({}, {}, {"active": 5.0, "none": 0.0}, "test")
    arms = [
        payer_arm("A", 1000, 100, 5.0, 100),
        payer_arm("B", 1000, 300, 5.0, 100),
        payer_arm("C", 1000, 280, 5.0, 100),
    ]
    out = build_verdict(make_test(arms), cal)
    assert out["leader"] == "B"
    assert out["p2bb_expected"] == round(p2bb(pseudo_values(arms[2], cal), pseudo_values(arms[1], cal)), 4)
    assert out["p2bb_expected"] < 0.95


def test_leader_tie_goes_to_first_arm():
    out = v(fake(equal=True))
    assert out["leader"] == "A"


def test_raw_and_expected_both_reported():
    cal = Calibration({}, {}, {"active": 10.0, "none": 0.0}, "test")
    a = Arm("A", [Group("active", "m", 5.0, 200, 0.0), Group("none", "-", 5.0, 800, 0.0)], 100, 0, 200, 0, 0.0, {})
    k_b = min(range(101, 200), key=lambda k: abs(
        p2bb([10.0] * 200 + [0.0] * 800, [11.0] * k + [1.0] * (1000 - k)) - 0.6))
    b = Arm("B", [Group("active", "m", 5.0, k_b, 1.0), Group("none", "-", 5.0, 1000 - k_b, 1.0)], 100, 0, k_b, 0, 1000.0, {})
    out = build_verdict(make_test([a, b]), cal)
    assert out["leader"] == "B"
    assert out["p2bb_raw"] == 1.0
    assert out["p2bb_expected"] == pytest.approx(0.6, abs=0.02)


def test_next_step_fields():
    out = v(fake(p2bb=0.97, maturity=0.4))
    step = out["next_step"]
    assert step["placement_id"] == "placement-1"
    assert step["primary_metric"] == "net revenue per user, 60 days"
    assert step["watch"] == [] and step["alternative"] is None
    assert step["reason"]


def test_arms_breakdown():
    test, cal = fake(p2bb=0.8, maturity=0.5)
    out = build_verdict(test, cal, warnings={"B": [{"metric": "refund_rate_per_payer", "value": 0.1,
                                                    "vs_other": 0.05, "status": "ok"}]})
    arm_b = out["arms"][1]
    est = estimate(test.arms[1], cal)
    assert arm_b["title"] == "B" and arm_b["users"] == 1000
    assert arm_b["revenue_received"] == round(est.received, 2)
    assert arm_b["revenue_expected_trials"] == round(est.from_trials, 2)
    assert arm_b["revenue_expected_renewals"] == round(est.from_renewals, 2)
    assert arm_b["warnings"][0]["metric"] == "refund_rate_per_payer"
    assert out["arms"][0]["warnings"] == []


def test_segments_passed_through():
    found = [{"dimension": "platform", "value": "ios", "p": 0.01}]
    out = v(fake(), segments=(17, found))
    assert out["segments_checked"] == 17 and out["segments_found"] == found
    default = v(fake())
    assert default["segments_checked"] == 0 and default["segments_found"] == []


def test_sources_reported():
    out = v(fake())
    assert out["source"] == "offline" and out["calibration_source"] == "test"
    assert out["ab_test_id"] == "test-1"


def test_empty_test_maturity_is_one():
    cal = Calibration({}, {}, {}, "test")
    arms = [Arm("A", [], 0, 0, 0, 0, 0.0, {}), Arm("B", [], 0, 0, 0, 0, 0.0, {})]
    out = build_verdict(make_test(arms), cal)
    assert out["maturity"] == 1.0 and out["verdict"] == "not_enough_data"
    assert out["money_at_stake_usd"] == 0


@pytest.mark.parametrize("kwargs", [
    {"events": [12, 80]},
    {"p2bb": 0.97, "maturity": 0.4},
    {"p2bb": 0.7, "maturity": 0.5},
    {"p2bb": 0.7, "maturity": 0.9},
    {"users": [0, 100]},
])
def test_output_matches_schema(kwargs):
    out = v(fake(**kwargs), segments=(3, []))
    check(json.loads(json.dumps(out)), SCHEMA)
    assert set(out) == set(SCHEMA["required"])


def test_schema_rejects_bad_verdict():
    out = v(fake())
    out["verdict"] = "maybe"
    with pytest.raises(AssertionError):
        check(out, SCHEMA)

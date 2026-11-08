import json
from pathlib import Path

import pytest

from eval.check_agent_text import check
from verdict_agent import service
from verdict_agent.card import render_card
from verdict_agent.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
SYNTH = FIXTURES / "synthetic" / "day14"
SYNTH_ID = "50e46448-6692-54c6-b1e0-1b2e2fa62cdd"
ONBOARDING = FIXTURES / "live" / "995b124f-9075-440d-83bb-20dbdf7d7fbb"

TOO_EARLY = {
    "ab_test_id": "t", "verdict": "not_enough_data", "reason": "min_events", "leader": "B",
    "p2bb_expected": 0.6388, "p2bb_raw": 0.6871, "maturity": 0.9171, "horizon_days": 60,
    "come_back_on": "2027-01-05",
    "arms": [{"title": "A", "users": 40, "revenue_received": 1.25, "revenue_expected_trials": 0.1,
              "revenue_expected_renewals": 0.24, "revenue_expected_total": 1.59},
             {"title": "B", "users": 37, "revenue_received": 2.7, "revenue_expected_trials": 0.0,
              "revenue_expected_renewals": 0.0, "revenue_expected_total": 2.7}],
    "calibration_source": "product", "expected_gap_per_user": 1.11, "money": None,
    "next_action": "come_back", "next_action_basis": "verdict",
}


def synth_verdict():
    return service.verdict(SYNTH_ID, replay=str(SYNTH))


def test_card_for_the_synthetic_trap():
    card = render_card(synth_verdict())
    assert card.startswith("SHIP weekly_trial")
    for piece in ("0.9999", "raw 0.0", "60-day horizon", "$180.05", "$0.2"):
        assert piece in card


def test_card_survives_missing_fields():
    card = render_card({"verdict": "keep_running", "leader": "B", "p2bb_expected": 0.5,
                        "arms": [{"title": "B"}], "health": {"srm": True}, "next_action": "fix_test"})
    assert card.startswith("FIX TEST · sample ratio mismatch")


def test_card_for_a_test_that_is_too_early():
    card = render_card(TOO_EARLY)
    assert card.startswith("WAIT until 2027-01-05")
    assert "$" in card  # per-user revenue of the leader
    assert "loss" not in card and "costs" not in card


@pytest.mark.parametrize("verdict", [TOO_EARLY, "synth", "onboarding"])
def test_every_number_in_the_card_comes_from_the_json(verdict):
    if verdict == "synth":
        verdict = synth_verdict()
    elif verdict == "onboarding":
        verdict = service.verdict(ONBOARDING.name, replay=str(ONBOARDING))
    result = check(verdict, render_card(verdict))
    assert result["unmatched"] == []
    assert result["verdict_ok"]


def test_ship_either_and_wait_without_date():
    tie = dict(TOO_EARLY, verdict="tie", reason=None, come_back_on=None, next_action="ship_either")
    assert render_card(tie).startswith("SHIP EITHER")
    nodate = dict(TOO_EARLY, come_back_on=None)
    assert render_card(nodate).startswith("WAIT ·")


def test_card_error():
    assert render_card({"error": "rate limited"}) == "ERROR: rate limited"


def test_cli_prints_the_card(capsys):
    code = main([SYNTH_ID, "--replay", str(SYNTH), "--format", "card"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("SHIP weekly_trial")


def test_cli_card_error_exits_non_zero(capsys):
    code = main(["x", "--replay", str(SYNTH), "--horizon", "0", "--format", "card"])
    assert code == 1
    assert capsys.readouterr().out.startswith("ERROR: ")


def test_cli_default_is_json(capsys):
    main([SYNTH_ID, "--replay", str(SYNTH)])
    assert json.loads(capsys.readouterr().out)["leader"] == "weekly_trial"

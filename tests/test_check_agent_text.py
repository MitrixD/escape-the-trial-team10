import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "eval" / "check_agent_text.py"
RUNS = ROOT / "eval" / "agent_runs"
RUN_NAMES = ["replay_synthetic_day14", "replay_onboarding", "live_onboarding"]

VERDICT = {
    "ab_test_id": "test-1",
    "verdict": "keep_running",
    "reason": "pending_revenue",
    "leader": "B",
    "p2bb_expected": 0.8353,
    "p2bb_raw": 0.9712,
    "maturity": 0.4227,
    "horizon_days": 60,
    "come_back_on": "2026-11-21",
    "arms": [
        {"title": "A", "users": 1400, "revenue_received": 3.77, "revenue_expected_trials": 0.0,
         "revenue_expected_renewals": -0.01, "revenue_expected_total": 3.76},
        {"title": "B", "users": 1385, "revenue_received": 1.01, "revenue_expected_trials": 0.71,
         "revenue_expected_renewals": 3.55, "revenue_expected_total": 5.27},
    ],
    "calibration_source": "product",
    "expected_gap_per_user": 1.51,
}


def _load():
    spec = importlib.util.spec_from_file_location("check_agent_text", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_numbers_found_with_rounding_and_percent():
    text = "**Keep running**: P2BB 84%, maturity about 42%, 1,400 users, $5.27 vs $3.76, gap $1.51 per user."
    result = _load().check(VERDICT, text)
    assert result["unmatched"] == []
    assert result["passed"]


def test_fraction_date_and_negative_numbers():
    text = "Keep running. P2BB 0.84 (raw 97%), 60-day horizon, come back on 2026-11-21, renewals -0.01."
    result = _load().check(VERDICT, text)
    assert result["unmatched"] == []
    assert result["passed"]


def test_invented_number_fails():
    result = _load().check(VERDICT, "Keep running; the uplift is 12%.")
    assert result["unmatched"] == ["12%"]
    assert not result["passed"]


def test_wrong_date_fails():
    result = _load().check(VERDICT, "Keep running and come back on 2026-11-22.")
    assert result["unmatched"] == ["2026-11-22"]
    assert not result["passed"]


def test_bold_word_wins_over_earlier_plain_label():
    text = "The lead is not confirmed yet, so **keep running**."
    assert _load().check(VERDICT, text)["verdict_stated"] == "keep_running"


def test_wrong_verdict_word_fails():
    result = _load().check(VERDICT, "The verdict is **confirmed**, though you could keep running.")
    assert result["verdict_stated"] == "confirmed"
    assert not result["verdict_ok"]
    assert not result["passed"]


@pytest.mark.parametrize("text, label", [
    ("Not enough data yet.", "not_enough_data"),
    ("Verdict: not_enough_data.", "not_enough_data"),
    ("It is a tie.", "tie"),
    ("Verdict: keep_running.", "keep_running"),
    ("The result is confirmed.", "confirmed"),
])
def test_verdict_labels(text, label):
    assert _load().stated_verdict(text) == label


def test_no_verdict_word_fails():
    result = _load().check(VERDICT, "B looks better.")
    assert result["verdict_stated"] is None
    assert not result["passed"]


def test_request_numbers_count_as_known():
    checker = _load()
    assert checker.check(VERDICT, "Keep running for 90 days.")["unmatched"] == ["90"]
    assert checker.check(VERDICT, "Keep running for 90 days.", {"horizon": 90})["passed"]


def test_check_files(tmp_path):
    import json
    (tmp_path / "v.json").write_text(json.dumps(VERDICT))
    (tmp_path / "a.txt").write_text("**Keep running**, P2BB 84%.")
    assert _load().check_files(tmp_path / "v.json", tmp_path / "a.txt")["passed"]


@pytest.mark.parametrize("name", RUN_NAMES)
def test_recorded_agent_answers_pass(name):
    result = _load().check_files(RUNS / f"{name}.json", RUNS / f"{name}.txt", RUNS / f"{name}.request.json")
    assert result["unmatched"] == []
    assert result["verdict_ok"]


CONFIRMED = {**VERDICT, "verdict": "confirmed", "reason": None, "come_back_on": None}


@pytest.mark.parametrize("text", [
    "The lead of B is not confirmed.",
    "B leads, but it isn't confirmed yet.",
    "B is unconfirmed.",
    "B leads; this is not yet confirmed.",
])
def test_negated_confirmed_is_not_confirmed(text):
    result = _load().check(CONFIRMED, text)
    assert result["verdict_stated"] != "confirmed"
    assert not result["passed"]


@pytest.mark.parametrize("text, stated", [
    ("**Confirmed**: ship B.", "B"),
    ("**Confirmed**: B leads.", "B"),
    ("**Confirmed**: the winner is A.", "A"),
    ("**Confirmed**. Ship A now.", "A"),
    ("**Confirmed**, 1,400 users.", None),
])
def test_stated_leader(text, stated):
    assert _load().check(CONFIRMED, text)["leader_stated"] == stated


def test_wrong_leader_fails():
    result = _load().check(CONFIRMED, "**Confirmed**: ship A.")
    assert result["leader_expected"] == "B"
    assert not result["leader_ok"]
    assert not result["passed"]


def test_leader_with_a_long_title_is_found():
    verdict = {**CONFIRMED, "leader": "weekly_trial",
               "arms": [{"title": "annual_upfront"}, {"title": "weekly_trial"}]}
    result = _load().check(verdict, "**Confirmed**: weekly_trial leads annual_upfront.")
    assert result["leader_stated"] == "weekly_trial"
    assert result["passed"]


@pytest.mark.parametrize("text, stated", [
    ("annual_upfront leads on received revenue, but weekly_trial wins over 60 days. **Confirmed**: ship weekly_trial.",
     "weekly_trial"),
    ("**Confirmed**: do not ship annual_upfront; ship weekly_trial.", "weekly_trial"),
])
def test_ship_phrase_wins_over_raw_lead_and_negated_ship(text, stated):
    verdict = {**CONFIRMED, "leader": "weekly_trial", "arms": [{"title": "annual_upfront"}, {"title": "weekly_trial"}]}
    result = _load().check(verdict, text)
    assert result["leader_stated"] == stated
    assert result["passed"]


@pytest.mark.parametrize("text", ["There is no confirmed winner yet; keep the test running.",
                                  "The lead cannot be confirmed yet."])
def test_more_negations_are_not_confirmed(text):
    assert _load().check(CONFIRMED, text)["verdict_stated"] != "confirmed"

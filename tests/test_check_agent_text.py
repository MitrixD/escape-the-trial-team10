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

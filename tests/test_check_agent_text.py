import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "eval" / "check_agent_text.py"
RUNS = ROOT / "eval" / "agent_runs"

VERDICT = {
    "ab_test_id": "Main: 3 plans vs lifetime anchor (NA)",
    "verdict": "early",
    "leader": "B",
    "p2bb_expected": 0.8353,
    "maturity": 0.7519,
    "come_back_on": "2026-11-21",
    "money_at_stake_usd": 4641.15,
    "arms": [{"title": "B", "users": 1400, "revenue_received": 5.36, "revenue_expected_renewals": -0.01}],
    "next_step": {"primary_metric": "net revenue per user, 60 days"},
}


def _load():
    spec = importlib.util.spec_from_file_location("check_agent_text", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_numbers_found_with_rounding_and_percent():
    result = _load().check(VERDICT, "It is **early**: P2BB 84%, maturity about 75%, $4,641 at stake, 1,400 users, $5.36.")
    assert result["unmatched"] == []
    assert result["passed"]


def test_fraction_and_date_and_string_numbers():
    text = "The verdict is early. P2BB 0.84, come back on 2026-11-21, 60-day goal, 3 plans, renewals -0.01."
    result = _load().check(VERDICT, text)
    assert result["unmatched"] == []
    assert result["passed"]


def test_invented_number_fails():
    result = _load().check(VERDICT, "The verdict is early and the uplift is 12%.")
    assert result["unmatched"] == ["12%"]
    assert not result["passed"]


def test_wrong_date_fails():
    result = _load().check(VERDICT, "The verdict is early; come back on 2026-11-22.")
    assert result["unmatched"] == ["2026-11-22"]


def test_wrong_verdict_word_fails():
    result = _load().check(VERDICT, "The verdict is **confirmed**, though it looks early.")
    assert result["verdict_stated"] == "confirmed"
    assert not result["verdict_ok"]
    assert not result["passed"]


def test_not_enough_data_phrase():
    result = _load().check({**VERDICT, "verdict": "not_enough_data"}, "Not enough data yet.")
    assert result["verdict_stated"] == "not_enough_data"
    assert result["passed"]


def test_request_numbers_count_as_known():
    checker = _load()
    assert checker.check(VERDICT, "Early at day 17.")["unmatched"] == ["17"]
    assert checker.check(VERDICT, "Early at day 17.", {"day": 17})["passed"]


@pytest.mark.parametrize("name", ["live_onboarding", "offline_settings_day14", "offline_main_day14"])
def test_recorded_agent_answers_pass(name):
    result = _load().check_files(RUNS / f"{name}.json", RUNS / f"{name}.txt", RUNS / f"{name}.request.json")
    assert result["unmatched"] == []
    assert result["verdict_ok"]


def test_settings_answer_strict_json_only_flags_day():
    result = _load().check_files(RUNS / "offline_settings_day14.json", RUNS / "offline_settings_day14.txt")
    assert result["unmatched"] == ["14"]

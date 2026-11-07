import io
import json
from pathlib import Path

import pytest

from verdict_agent import guard

FIXTURES = Path(__file__).parent / "fixtures"
SYNTH = FIXTURES / "synthetic" / "day14"
SYNTH_ID = "50e46448-6692-54c6-b1e0-1b2e2fa62cdd"
ONBOARDING = FIXTURES / "live" / "995b124f-9075-440d-83bb-20dbdf7d7fbb"
ONB_ID = ONBOARDING.name
ONB_B = "776b28bb-1a9a-4610-948b-f74f7842a464"
ONB_A = "fc4f9fe6-5a00-4abe-aba0-f8c31839a21a"
APP = "59483555-8237-45f5-aeb7-99552db3bdcd"


def mcp_stop(test_id, winner=None, kind="flow"):
    tool_input = {"app_id": APP, "ab_test_id": test_id}
    if winner:
        tool_input[f"winner_{kind}_id"] = winner
    return {"hook_event_name": "PreToolUse", "tool_name": "mcp__adapty__ab_tests_stop", "tool_input": tool_input}


def bash(command):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}


def run(monkeypatch, capsys, payload, replay=(SYNTH, ONBOARDING), mode="strict", argv=None):
    monkeypatch.setenv("VERDICT_GUARD_REPLAY", ":".join(str(p) for p in replay))
    if mode is None:
        monkeypatch.delenv("VERDICT_GUARD_MODE", raising=False)
    else:
        monkeypatch.setenv("VERDICT_GUARD_MODE", mode)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    code = guard.main(argv or [])
    out = capsys.readouterr().out
    assert code == 0
    return json.loads(out)["hookSpecificOutput"] if out.strip() else None


def test_agent_picking_the_raw_favourite_is_denied(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"))
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    assert "weekly_trial" in reason and "annual_upfront" in reason and "0.9994" in reason


def test_winner_that_agrees_with_the_verdict_asks_a_human(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_B))
    assert out["permissionDecision"] == "ask"
    assert "B" in out["permissionDecisionReason"] and "0.9999" in out["permissionDecisionReason"]


def test_other_arm_on_live_bundle_is_denied(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_A))
    assert out["permissionDecision"] == "deny"


def test_too_early_is_denied_with_the_date(monkeypatch, capsys):
    early = {"verdict": "keep_running", "leader": "B", "p2bb_expected": 0.7, "come_back_on": "2026-12-14",
             "next_action": "come_back", "next_action_basis": "verdict",
             "money": {"cost_per_day": 57.58, "loss_if_ship_leader_now": 3273.16, "chance_leader_is_wrong": 0.3}}
    monkeypatch.setattr(guard, "safe_verdict", lambda **kw: early)
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_B))
    assert out["permissionDecision"] == "deny"
    assert "2026-12-14" in out["permissionDecisionReason"] and "57.58" in out["permissionDecisionReason"]


def test_no_verdict_no_stop(monkeypatch, capsys):
    monkeypatch.setattr(guard, "safe_verdict", lambda **kw: {"error": "rate limited"})
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_B))
    assert out["permissionDecision"] == "deny"
    assert "rate limited" in out["permissionDecisionReason"]


def test_guard_crash_is_denied(monkeypatch, capsys):
    def boom(**kw):
        raise RuntimeError("x")
    monkeypatch.setattr(guard, "safe_verdict", boom)
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_B))
    assert out["permissionDecision"] == "deny"


def test_stop_without_a_winner_asks(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID))
    assert out["permissionDecision"] == "ask"


@pytest.mark.parametrize("command", [
    f"adapty ab-tests stop {SYNTH_ID} --app {APP} --winner annual_upfront --yes",
    f"adapty ab-tests stop --app={APP} --winner=annual_upfront {SYNTH_ID} -y --json",
    f"cd /tmp && adapty ab-tests stop --app {APP} {SYNTH_ID} --winner annual_upfront",
])
def test_cli_stop_is_guarded_too(monkeypatch, capsys, command):
    out = run(monkeypatch, capsys, bash(command))
    assert out["permissionDecision"] == "deny"
    assert "weekly_trial" in out["permissionDecisionReason"]


@pytest.mark.parametrize("command", ["ls -la", f"adapty ab-tests get {SYNTH_ID} --app {APP} --json",
                                     "echo 'ab-tests stop'"])
def test_other_commands_pass(monkeypatch, capsys, command):
    assert run(monkeypatch, capsys, bash(command)) is None


def test_bundle_is_picked_by_test_id(monkeypatch):
    monkeypatch.setenv("VERDICT_GUARD_REPLAY", f"{ONBOARDING}:{SYNTH}")
    assert guard.replay_for(SYNTH_ID) == SYNTH
    assert guard.replay_for("00000000-0000-0000-0000-000000000000") is None


def test_strict_deny_tells_how_the_user_can_override(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"))
    assert "VERDICT_GUARD_MODE=ask" in out["permissionDecisionReason"]


def test_ask_mode_hands_a_disagreeing_stop_to_the_human(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"), mode="ask")
    assert out["permissionDecision"] == "ask"
    reason = out["permissionDecisionReason"]
    assert reason.startswith("WARNING")
    assert "weekly_trial" in reason and "annual_upfront" in reason


def test_ask_mode_without_a_verdict_still_asks_with_a_warning(monkeypatch, capsys):
    monkeypatch.setattr(guard, "safe_verdict", lambda **kw: {"error": "rate limited"})
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_B), mode="ask")
    assert out["permissionDecision"] == "ask"
    assert out["permissionDecisionReason"].startswith("WARNING") and "rate limited" in out["permissionDecisionReason"]


def test_ask_mode_agreeing_stop_has_no_warning(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(ONB_ID, ONB_B), mode="ask")
    assert out["permissionDecision"] == "ask"
    assert not out["permissionDecisionReason"].startswith("WARNING")


def test_default_mode_is_ask(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"), mode=None)
    assert out["permissionDecision"] == "ask"


def test_command_mode_applies_without_env(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"), mode=None, argv=["--mode", "strict"])
    assert out["permissionDecision"] == "deny"


def test_the_human_sets_the_mode_not_the_command(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"), mode="ask", argv=["--mode", "strict"])
    assert out["permissionDecision"] == "ask"


def test_unknown_mode_is_strict(monkeypatch, capsys):
    out = run(monkeypatch, capsys, mcp_stop(SYNTH_ID, "annual_upfront"), mode="off")
    assert out["permissionDecision"] == "deny"

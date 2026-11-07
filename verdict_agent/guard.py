"""Claude Code PreToolUse hook: an Adapty A/B test stop needs the verdict's agreement and a human's yes."""
import json
import os
import shlex
import sys
from pathlib import Path

from verdict_agent.adapty_cli import AdaptyCLI, replay_runner
from verdict_agent.live import _arms, read_test
from verdict_agent.service import safe_verdict

STOP_TOOL_SUFFIX = "__ab_tests_stop"
MODES = ("ask", "strict")
DEFAULT_MODE = "ask"
OVERRIDE_HINT = (" If the user insists, they can restart the session with VERDICT_GUARD_MODE=ask"
                 " and confirm the stop themselves.")
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")"}


def replay_for(test_id: str) -> Path | None:
    for entry in filter(None, os.environ.get("VERDICT_GUARD_REPLAY", "").split(os.pathsep)):
        path = Path(entry)
        try:
            recorded = json.loads((path / "ab-tests_get.json").read_text())
        except (OSError, ValueError):
            continue
        if recorded.get("data", recorded).get("ab_test_id") == test_id:
            return path
    return None


def _flag(words: list[str], i: int, name: str) -> tuple[str | None, int]:
    word = words[i]
    if word == name:
        return (words[i + 1] if i + 1 < len(words) else None), i + 2
    return word.split("=", 1)[1], i + 1


def parse_cli_stop(command: str) -> dict | None:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return None
    for i in range(len(words) - 2):
        if Path(words[i]).name == "adapty" and words[i + 1:i + 3] == ["ab-tests", "stop"]:
            break
    else:
        return None
    stop = {"ab_test_id": None, "app_id": None, "winner": None}
    j = i + 3
    while j < len(words) and words[j] not in SEPARATORS:
        word = words[j]
        for name, key in (("--app", "app_id"), ("--winner", "winner")):
            if word == name or word.startswith(name + "="):
                stop[key], j = _flag(words, j, name)
                break
        else:
            if word == "--other" or word.startswith("--other="):
                _, j = _flag(words, j, "--other")
            elif word.startswith("-"):
                j += 1
            else:
                stop["ab_test_id"] = stop["ab_test_id"] or word
                j += 1
    return stop


def stop_request(payload: dict) -> dict | None:
    tool, args = payload.get("tool_name", ""), payload.get("tool_input") or {}
    if tool.startswith("mcp__") and tool.endswith(STOP_TOOL_SUFFIX):
        return {"ab_test_id": args.get("ab_test_id"), "app_id": args.get("app_id"),
                "winner": args.get("winner_flow_id") or args.get("winner_paywall_id")}
    if tool == "Bash":
        return parse_cli_stop(args.get("command", ""))
    return None


def _arm_title(test: dict, winner: str) -> str | None:
    arms, id_field = _arms(test)
    for arm in arms:
        if winner in (arm.get(id_field), arm.get("variation_id")):
            return arm.get("title") or arm.get("flow_name") or arm.get("paywall_name")
    return None


def _read_test(test_id: str, app_id: str | None, replay: Path | None) -> dict:
    cli = AdaptyCLI(runner=replay_runner(replay), min_interval=0) if replay else AdaptyCLI()
    return read_test(cli, app_id or "replay", test_id)


def _money(v: dict) -> str:
    m = v.get("money") or {}
    parts = [f"{label} ${m[key]}" for key, label in (("cost_per_day", "one more test day costs"),
                                                     ("loss_if_ship_leader_now", "shipping the leader now risks"))
             if m.get(key) is not None]
    if m.get("chance_leader_is_wrong") is not None:
        parts.append(f"chance the leader is wrong {m['chance_leader_is_wrong']}")
    return ("; " + ", ".join(parts)) if parts else ""


def decide(stop: dict) -> tuple[str, str]:
    test_id = stop.get("ab_test_id")
    if not test_id:
        return "deny", "Verdict guard: no A/B test ID in the stop call, so there is no verdict. Not stopping."
    replay = replay_for(test_id)
    v = safe_verdict(ab_test_id=test_id, app_id=stop.get("app_id"), replay=str(replay) if replay else None)
    if "error" in v:
        return "deny", f"Verdict guard: no verdict for test {test_id} ({v['error']}). An irreversible stop needs one."
    raw = f" (raw P2BB on received revenue {v['p2bb_raw']})" if v.get("p2bb_raw") is not None else ""
    head = (f"Verdict for {test_id}: {v['verdict']}, leader {v['leader']}, p2bb_expected {v['p2bb_expected']}{raw}"
            f"{_money(v)}.")
    action = v.get("next_action")
    if action == "come_back":
        when = f" Come back on {v['come_back_on']}." if v.get("come_back_on") else ""
        return "deny", f"{head} Too early to stop.{when} Ask the user before overriding."
    winner = stop.get("winner")
    if not winner:
        return "ask", f"{head} The stop names no winner of the test. Confirm the stop."
    chosen = _arm_title(_read_test(test_id, stop.get("app_id"), replay), winner)
    if chosen is None:
        return "ask", f"{head} Winner {winner} is not an arm of the test. Confirm the stop."
    if action == "ship_leader" and chosen != v["leader"]:
        return "deny", (f"{head} The chosen winner is {chosen}, but the verdict leader is {v['leader']}"
                        f" (p2bb_expected {v['p2bb_expected']}). Stop with {v['leader']} or ask the user.")
    basis = v.get("next_action_basis")
    return "ask", f"{head} Next action {action} (basis {basis}); chosen winner {chosen}. A stop cannot be undone."


def resolve_mode(argv: list[str]) -> str:
    mode = os.environ.get("VERDICT_GUARD_MODE")
    if mode is None and "--mode" in argv[:-1]:
        mode = argv[argv.index("--mode") + 1]
    mode = mode if mode is not None else DEFAULT_MODE
    return mode if mode in MODES else "strict"


def apply_mode(mode: str, decision: str, reason: str) -> tuple[str, str]:
    if decision != "deny":
        return decision, reason
    if mode == "ask":
        return "ask", "WARNING: this stop goes against the verdict or has no verdict. " + reason
    return "deny", reason + OVERRIDE_HINT


def _output(decision: str, reason: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                              "permissionDecisionReason": reason}})


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        stop = stop_request(json.load(sys.stdin))
    except ValueError:
        return 0
    if stop is None:
        return 0
    try:
        decision, reason = decide(stop)
    except Exception as exc:
        print(f"verdict-guard: {type(exc).__name__}", file=sys.stderr)
        decision, reason = "deny", f"Verdict guard failed ({type(exc).__name__}). Not stopping without a verdict."
    print(_output(*apply_mode(resolve_mode(argv), decision, reason)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

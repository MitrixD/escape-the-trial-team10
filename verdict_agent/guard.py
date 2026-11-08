"""Claude Code PreToolUse hook: an Adapty A/B test stop needs the verdict's agreement and a human's yes."""
import json
import os
import re
import shlex
import sys
from pathlib import Path

from verdict_agent.adapty_cli import AdaptyCLI, replay_runner
from verdict_agent.live import _arms, read_test
from verdict_agent.card import render_card
from verdict_agent.service import safe_verdict

ENDING_SUBCOMMANDS = ("stop", "replace", "archive")
READ_SUBCOMMANDS = ("get", "list", "metrics")
MODES = ("ask", "strict")
DEFAULT_MODE = "ask"
OVERRIDE_HINT = (" If the user insists, they can restart the session with VERDICT_GUARD_MODE=ask"
                 " and confirm the stop themselves.")
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", "\n"}
SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash", "eval"}
ENDING_WORD = re.compile(r"\b(stop|replace|archive)\b", re.I)
SHELL_EXPANSION = re.compile(r"[$`{}*?\[]")
ORDER = {None: 0, "ask": 1, "deny": 2}


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


def _words(command: str) -> list[str] | None:
    lexer = shlex.shlex(command.replace("\n", " \n "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return [w if w != "\\n" else "\n" for w in lexer]
    except ValueError:
        return None


def _is_adapty(word: str) -> bool:
    return Path(word).name.split("@", 1)[0].lower() == "adapty"


def _subcommand(words: list[str], i: int) -> tuple[str | None, int]:
    word = (words[i + 1] if i + 1 < len(words) else "").lower()
    if word.startswith("ab-tests:"):
        return word.split(":", 1)[1], i + 2
    if word == "ab-tests" and i + 2 < len(words):
        return words[i + 2].lower(), i + 3
    return None, i + 1


def _parse_call(words: list[str], j: int, sub: str) -> tuple[dict, int]:
    call = {"kind": "replace" if sub in ("replace", "archive") else "stop", "ab_test_id": None, "app_id": None,
            "winner": None, "other": sub in ("replace", "archive")}
    while j < len(words) and words[j] not in SEPARATORS:
        word = words[j]
        key = next((k for name, k in (("--app", "app_id"), ("--winner", "winner"), ("--other", "other"))
                    if word == name or word.startswith(name + "=")), None)
        if key:
            value = word.split("=", 1)[1] if "=" in word else (words[j + 1] if j + 1 < len(words) else None)
            j += 1 if "=" in word else 2
            call[key] = True if key == "other" else value
        elif word == "--no-content":
            call["other"], j = True, j + 1
        elif word.startswith("-"):
            j += 1
        else:
            call["ab_test_id"] = call["ab_test_id"] or word
            j += 1
    return call, j


def parse_cli_calls(command: str, depth: int = 0) -> list[dict]:
    words = _words(command)
    calls: list[dict] = []
    if words is None:
        return [{"kind": "unreadable"}] if _mentions_ending(command) else []
    i = 0
    while i < len(words):
        word = words[i]
        if _is_adapty(word):
            sub, j = _subcommand(words, i)
            if sub in ENDING_SUBCOMMANDS:
                call, i = _parse_call(words, j, sub)
                values = [v for v in (call["ab_test_id"], call["winner"], call["app_id"]) if isinstance(v, str)]
                readable = call["ab_test_id"] and not any(SHELL_EXPANSION.search(v) for v in values)
                calls.append(call if readable else {"kind": "unreadable"})
                continue
            if sub is not None and sub not in READ_SUBCOMMANDS and not sub.startswith("-") and sub != "--help":
                if SHELL_EXPANSION.search(sub):
                    calls.append({"kind": "unreadable"})
            i = j
            continue
        if Path(word).name in SHELL_WRAPPERS and depth < 2:
            k = i + 1
            while k < len(words) and words[k].startswith("-"):
                k += 1
            if k < len(words) and words[k] not in SEPARATORS:
                calls += parse_cli_calls(words[k], depth + 1)
                i = k + 1
                continue
        i += 1
    readable = [c for c in calls if c["kind"] != "unreadable"]
    if not readable and not calls and _mentions_ending(command):
        calls.append({"kind": "unreadable"})
    return calls


def _mentions_ending(text: str) -> bool:
    text = text.lower()
    return "adapty" in text and "ab-tests" in text and bool(ENDING_WORD.search(text))


def parse_cli_stop(command: str) -> dict | None:
    calls = [c for c in parse_cli_calls(command) if c["kind"] == "stop"]
    return calls[0] if calls else None


def requests_from(payload: dict) -> list[dict]:
    tool, args = payload.get("tool_name", ""), payload.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(args, dict):
        raise ValueError("malformed hook payload")
    if tool.startswith("mcp__") and tool.endswith("__ab_tests_stop"):
        other = bool(args.get("another_flow_id_to_run") or args.get("another_paywall_id_to_run"))
        return [{"kind": "stop", "ab_test_id": args.get("ab_test_id"), "app_id": args.get("app_id"),
                 "winner": args.get("winner_flow_id") or args.get("winner_paywall_id"), "other": other}]
    if tool.startswith("mcp__") and tool.endswith("__ab_tests_replace"):
        return [{"kind": "replace", "ab_test_id": args.get("ab_test_id"), "app_id": args.get("app_id"),
                 "winner": None, "other": True}]
    if tool.startswith("mcp__") and tool.endswith("__placements_update"):
        return [{"kind": "placement"}]
    if tool == "Bash":
        command = args.get("command", "")
        if not isinstance(command, str):
            raise ValueError("malformed Bash command")
        return parse_cli_calls(command)
    return []


def stop_request(payload: dict) -> dict | None:
    stops = [r for r in requests_from(payload) if r["kind"] == "stop"]
    return stops[0] if stops else None


def _arm_title(test: dict, winner: str) -> str | None:
    arms, id_field = _arms(test)
    for arm in arms:
        if winner in (arm.get(id_field), arm.get("variation_id")):
            return arm.get("title") or arm.get("flow_name") or arm.get("paywall_name")
    return None


def _read_test(test_id: str, app_id: str | None, replay: Path | None) -> dict:
    cli = AdaptyCLI(runner=replay_runner(replay), min_interval=0) if replay else AdaptyCLI()
    return read_test(cli, app_id or "replay", test_id)


def decide(stop: dict) -> tuple[str, str]:
    kind = stop.get("kind", "stop")
    if kind == "unreadable":
        return "deny", ("Verdict guard: this command mentions ending an A/B test with the Adapty CLI, but the guard "
                        "cannot read which test it would end and what it would show, so it cannot check it against "
                        "a verdict. To end a test, run the plain `adapty ab-tests stop <id> --app <app> --winner <id>`"
                        " with literal values. If this command does not end a test (a search, a commit message), "
                        "ask the user to run it.")
    if kind == "placement":
        return "ask", ("Verdict guard: changing a placement's audiences can end an A/B test running there. "
                       "Confirm that no running test is affected.")
    test_id = stop.get("ab_test_id")
    if not test_id:
        return "deny", "Verdict guard: no A/B test ID in the call, so there is no verdict. Not stopping."
    replay = replay_for(test_id)
    v = safe_verdict(ab_test_id=test_id, app_id=stop.get("app_id"), replay=str(replay) if replay else None)
    if "error" in v:
        return "deny", f"Verdict guard: no verdict for test {test_id} ({v['error']}). An irreversible stop needs one."
    head = f"Verdict for {test_id}: {render_card(v).replace(chr(10), ' | ')}."
    action = v.get("next_action")
    if action == "fix_test":
        return "deny", f"{head} The test is unhealthy, so its winner cannot be trusted: fix the split first."
    if action == "come_back":
        when = f" Come back on {v['come_back_on']}." if v.get("come_back_on") else ""
        return "deny", f"{head} Too early to stop.{when} Ask the user before overriding."
    if stop.get("other"):
        what = "replaces the test" if kind == "replace" else "shows other content instead of a winner"
        if action == "ship_leader":
            return "deny", (f"{head} This call {what}, but the verdict leader is {v['leader']}"
                            f" (p2bb_expected {v['p2bb_expected']}). Stop with {v['leader']} or ask the user.")
        return "ask", f"{head} This call {what}. Confirm it: it cannot be undone."
    winner = stop.get("winner")
    if not winner:
        return "ask", f"{head} The stop names nothing to show. Confirm the stop."
    chosen = _arm_title(_read_test(test_id, stop.get("app_id"), replay), winner)
    if chosen is None:
        return "ask", f"{head} Winner {winner} is not an arm of the test. Confirm the stop."
    if action == "ship_leader" and chosen != v["leader"]:
        return "deny", (f"{head} The chosen winner is {chosen}, but the verdict leader is {v['leader']}"
                        f" (p2bb_expected {v['p2bb_expected']}). Stop with {v['leader']} or ask the user.")
    basis = v.get("next_action_basis")
    return "ask", f"{head} Next action {action} (basis {basis}); chosen winner {chosen}. A stop cannot be undone."


def decide_all(requests: list[dict]) -> tuple[str | None, str]:
    worst, reasons = None, []
    for request in requests:
        decision, reason = decide(request)
        reasons.append(reason)
        if ORDER[decision] > ORDER[worst]:
            worst = decision
    return worst, " || ".join(reasons)


def resolve_mode(argv: list[str]) -> str:
    mode = os.environ.get("VERDICT_GUARD_MODE")
    if mode is None:
        for i, arg in enumerate(argv):
            if arg == "--mode" and i + 1 < len(argv):
                mode = argv[i + 1]
            elif arg.startswith("--mode="):
                mode = arg.split("=", 1)[1]
    mode = mode if mode is not None else DEFAULT_MODE
    return mode if mode in MODES else "strict"


def apply_mode(mode: str, decision: str, reason: str) -> tuple[str, str]:
    if decision != "deny":
        return decision, reason
    if mode == "ask":
        return "ask", ("WARNING: this call goes against the verdict, has no verdict or cannot be checked. "
                       + reason)
    return "deny", reason + OVERRIDE_HINT


def _output(decision: str, reason: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                              "permissionDecisionReason": reason}})


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    mode = resolve_mode(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not an object")
        requests = requests_from(payload)
        if not requests:
            return 0
        decision, reason = decide_all(requests)
    except Exception as exc:
        print(f"verdict-guard: {type(exc).__name__}", file=sys.stderr)
        decision, reason = "deny", f"Verdict guard failed ({type(exc).__name__}). Not letting the call through."
    print(_output(*apply_mode(mode, decision, reason)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

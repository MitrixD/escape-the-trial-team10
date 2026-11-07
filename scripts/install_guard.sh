#!/usr/bin/env bash
# Install the Verdict stop guard into another project: writes <dir>/.claude/settings.json.
# Mode: ask (default) sends every A/B test stop to a human, with a warning when it goes against the verdict;
# strict denies such stops. VERDICT_GUARD_MODE at session start overrides it.
set -euo pipefail
usage="usage: scripts/install_guard.sh <project dir> [--mode ask|strict]"
target="${1:?$usage}"
mode="ask"
if [ "${2:-}" = "--mode" ]; then
  mode="${3:?$usage}"
elif [ -n "${2:-}" ]; then
  echo "$usage" >&2
  exit 2
fi
case "$mode" in ask|strict) ;; *) echo "unknown mode $mode: use ask or strict" >&2; exit 2 ;; esac
repo="$(cd "$(dirname "$0")/.." && pwd)"
settings="$target/.claude/settings.json"
if [ -e "$settings" ]; then
  echo "refusing to overwrite $settings: add the PreToolUse hooks from $repo/.claude/settings.json by hand" >&2
  exit 1
fi
mkdir -p "$target/.claude"
python3 - "$repo" "$settings" "$mode" <<'PY'
import json, shlex, sys
repo, path, mode = sys.argv[1:4]
command = f"cd {shlex.quote(repo)} && .venv/bin/python -m verdict_agent.guard --mode {mode}"
hook = {"type": "command", "command": command, "timeout": 120}
settings = {"hooks": {"PreToolUse": [{"matcher": "mcp__.*adapty.*__ab_tests_stop", "hooks": [hook]},
                                     {"matcher": "Bash", "hooks": [hook]}]}}
with open(path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PY
echo "installed the stop guard ($mode mode) into $settings"

#!/usr/bin/env bash
# Set up Verdict Agent in one command and report what works. Safe to run again. Never writes to Adapty.
#
#   scripts/setup.sh                      venv, dependencies, tests, a verdict on recorded data
#   scripts/setup.sh --guard DIR [--guard-mode ask|strict]   also install the stop guard into DIR
#   scripts/setup.sh --mcp DIR            also write DIR/.mcp.json for the verdict MCP tool
#   scripts/setup.sh --live               also check the Adapty CLI login and .env for live reads
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
guard_dir="" guard_mode="ask" mcp_dir="" live=0
usage="usage: scripts/setup.sh [--guard DIR] [--guard-mode ask|strict] [--mcp DIR] [--live]"
while [ $# -gt 0 ]; do
  case "$1" in
    --guard) guard_dir="${2:?$usage}"; shift 2 ;;
    --guard-mode) guard_mode="${2:?$usage}"; shift 2 ;;
    --mcp) mcp_dir="${2:?$usage}"; shift 2 ;;
    --live) live=1; shift ;;
    -h|--help) echo "$usage"; exit 0 ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done

ok() { printf '  [ok]   %s\n' "$1"; }
no() { printf '  [fail] %s\n' "$1"; failed=1; }
todo() { printf '  [todo] %s\n' "$1"; }
failed=0
cd "$repo"

echo "1. Python 3.10 or newer"
python=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    python="$candidate"; break
  fi
done
if [ -z "$python" ]; then
  no "no Python 3.10+ found: install it (for example from python.org) and run this script again"
  exit 1
fi
ok "$("$python" --version)"

echo "2. Virtual environment and dependencies"
[ -x .venv/bin/python ] || "$python" -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt
ok ".venv with requirements.txt"

echo "3. Tests (no network)"
if summary="$(.venv/bin/pytest -q 2>&1 | tail -1)" && [[ "$summary" == *passed* && "$summary" != *failed* ]]; then
  ok "pytest: $summary"
else
  no "pytest: $summary"
fi

echo "4. A verdict on recorded data (the synthetic test where raw P2BB picks the wrong variant)"
if .venv/bin/python -m verdict_agent.cli 50e46448-6692-54c6-b1e0-1b2e2fa62cdd \
     --replay tests/fixtures/synthetic/day14 --format card | sed 's/^/         /'; then
  ok "decision card printed"
else
  no "the CLI failed on the replay bundle"
fi

if [ -n "$guard_dir" ]; then
  echo "5. Stop guard in $guard_dir ($guard_mode mode)"
  if [ -e "$guard_dir/.claude/settings.json" ]; then
    todo "$guard_dir/.claude/settings.json exists: add the hooks from .claude/settings.json by hand"
  elif scripts/install_guard.sh "$guard_dir" --mode "$guard_mode" >/dev/null; then
    ok "installed; try it: cd $guard_dir && VERDICT_GUARD_REPLAY=$repo/tests/fixtures/synthetic/day14 claude"
  else
    no "install_guard.sh failed"
  fi
fi

if [ -n "$mcp_dir" ]; then
  echo "6. MCP config in $mcp_dir"
  if [ -e "$mcp_dir/.mcp.json" ]; then
    todo "$mcp_dir/.mcp.json exists: add the verdict-agent server from .mcp.json.example by hand"
  else
    mkdir -p "$mcp_dir"
    sed "s#<absolute path to this repo>#$repo#g" .mcp.json.example > "$mcp_dir/.mcp.json"
    ok "wrote $mcp_dir/.mcp.json (server verdict-agent, tool ab_test_verdict)"
  fi
fi

if [ "$live" = 1 ]; then
  echo "7. Live reads from your own Adapty account"
  if ! command -v adapty >/dev/null 2>&1; then
    todo "install the Adapty CLI: npm install -g adapty@latest"
  elif ! adapty auth whoami >/dev/null 2>&1; then
    todo "log in with your own account: adapty auth login"
  else
    ok "Adapty CLI logged in"
    [ -e .env ] || { cp .env.example .env; todo "created .env from .env.example"; }
    for key in ADAPTY_APP_ID ADAPTY_EXPECTED_COMPANY; do
      if grep -Eq "^$key=.+" .env; then ok "$key is set in .env"; else todo "set $key in .env"; fi
    done
    todo "find a test: adapty ab-tests list --app <app id> --type flow --json"
    todo "then: .venv/bin/python -m verdict_agent.cli <test id> --format card"
  fi
fi

echo
if [ "$failed" = 0 ]; then echo "Ready. Next: README.md, section 'For judges'."; else echo "Some steps failed, see above."; fi
exit "$failed"

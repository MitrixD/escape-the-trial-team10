#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

TEST_ID="${1:?usage: scripts/record_fixtures.sh <ab_test_id>}"
HISTORY_FROM="${HISTORY_FROM:-2026-07-01}"

env_val() {
  local val
  val="$(grep -E "^$1=" .env | head -1 | cut -d= -f2-)"
  val="${val%\"}"; val="${val#\"}"
  printf '%s' "$val"
}
APP="$(env_val ADAPTY_APP_ID)"
EXPECTED="$(env_val ADAPTY_EXPECTED_COMPANY)"
[ -n "$APP" ] || { echo "ADAPTY_APP_ID missing in .env" >&2; exit 2; }

OUT="tests/fixtures/live/$TEST_ID"
mkdir -p "$OUT"
RAW="$(mktemp -d)"
trap 'rm -rf "$RAW"' EXIT

call() {
  local name="$1"; shift
  [ -f "$OUT/$name.json" ] && return 0
  set +e
  adapty "$@" --json >"$RAW/$name.json" 2>"$RAW/$name.err"
  local rc=$?
  set -e
  sleep 1
  if [ $rc -eq 4 ] || grep -q '429' "$RAW/$name.err"; then
    echo "stopping on $name: exit $rc, stderr: $(head -c 300 "$RAW/$name.err")" >&2
    exit 4
  fi
  if [ $rc -ne 0 ]; then
    echo "$name failed with exit $rc: $(head -c 300 "$RAW/$name.err")" >&2
    return 1
  fi
  cp "$RAW/$name.json" "$OUT/$name.json"
}

if [ ! -f "$OUT/auth_whoami.json" ]; then
  adapty auth whoami --json >"$RAW/whoami.json"
  sleep 1
  python3 - "$RAW/whoami.json" "$OUT/auth_whoami.json" "$EXPECTED" <<'PY'
import json, sys
raw = open(sys.argv[1]).read()
expected = sys.argv[3]
matched = bool(expected) and expected.lower() in raw.lower()
json.dump({"company": "<redacted>", "matched_expected_company": matched}, open(sys.argv[2], "w"), indent=2)
PY
fi

call ab-tests_get ab-tests get "$TEST_ID" --app "$APP"
TYPE="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['type'])" "$OUT/ab-tests_get.json")"
call ab-tests_metrics_total ab-tests metrics total "$TEST_ID" --app "$APP" --type "$TYPE"
call products_list products list --app "$APP" --page-size 100

python3 - "$OUT/ab-tests_get.json" >"$RAW/ids.txt" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print((d.get("placement") or {}).get("placement_id", ""))
print(d["started_at"][:10])
for key in ("flows", "paywalls"):
    for arm in d.get(key) or []:
        ident = arm.get("flow_id") or arm.get("paywall_id")
        if ident:
            print(f"{key[:-1]}_id {ident}")
PY
PLACEMENT="$(sed -n 1p "$RAW/ids.txt")"
START="$(sed -n 2p "$RAW/ids.txt")"
TODAY="$(date +%F)"
HISTORY_TO="$(python3 -c "import datetime,sys; print(datetime.date.fromisoformat(sys.argv[1]) - datetime.timedelta(days=1))" "$START")"

sed -n '3,$p' "$RAW/ids.txt" | while read -r DIM ID; do
  call "analytics_funnel_$ID" analytics funnel --app "$APP" --date-from "$START" --date-to "$TODAY" \
    --filter "$DIM=$ID" --filter "placement_id=$PLACEMENT" --group-by store_product_id
done

call analytics_conversion_trial-paid analytics conversion --app "$APP" --conversion trial-paid \
  --group-by store_product_id --date-from "$HISTORY_FROM" --date-to "$HISTORY_TO"
call analytics_cohort analytics cohort --app "$APP" --date-from "$HISTORY_FROM" --date-to "$HISTORY_TO" \
  --granularity month --period-type renewals
call analytics_ltv analytics ltv --app "$APP" --date-from "$HISTORY_FROM" --date-to "$HISTORY_TO" \
  --group-by store_product_id --period-type days

echo "recorded $OUT"

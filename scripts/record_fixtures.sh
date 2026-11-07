#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for key in LUMEN_APP_ID ADAPTY_EXPECTED_COMPANY; do
  val="$(grep -E "^$key=" .env | head -1 | cut -d= -f2-)"
  val="${val%\"}"; val="${val#\"}"
  export "$key=$val"
done

TEST_ID="${ONBOARDING_TEST_ID:-995b124f-9075-440d-83bb-20dbdf7d7fbb}"
START="${TEST_START:-2026-11-07}"
TODAY="$(date +%F)"
OUT=tests/fixtures/live
mkdir -p "$OUT"
RAW="$(mktemp -d)"
trap 'rm -rf "$RAW"' EXIT

call() {
  local name="$1"; shift
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
    echo "$name failed with exit $rc" >&2
    return 1
  fi
}

if [ ! -f "$OUT/whoami.json" ]; then
call whoami auth whoami
python3 - "$RAW/whoami.json" "$OUT/whoami.json" <<'PY'
import json, os, sys
raw = open(sys.argv[1]).read()
expected = os.environ.get("ADAPTY_EXPECTED_COMPANY", "")
matched = bool(expected) and expected.lower() in raw.lower()
json.dump({"company": "<redacted>", "matched_expected_company": matched}, open(sys.argv[2], "w"), indent=2)
PY
fi

if [ ! -f "$OUT/ab_test_get.json" ]; then
call ab_test_get ab-tests get "$TEST_ID" --app "$LUMEN_APP_ID"
cp "$RAW/ab_test_get.json" "$OUT/ab_test_get.json"
fi
if [ ! -f "$OUT/ab_test_metrics_total.json" ]; then
call ab_test_metrics_total ab-tests metrics total "$TEST_ID" --app "$LUMEN_APP_ID" --type flow
cp "$RAW/ab_test_metrics_total.json" "$OUT/ab_test_metrics_total.json"
fi
cp "$OUT/ab_test_get.json" "$RAW/ab_test_get.json"

python3 - "$RAW/ab_test_get.json" >"$RAW/ids.txt" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d = d.get("data", d)
placement = (d.get("placement") or {}).get("placement_id")
flows = []
def walk(x):
    if isinstance(x, dict):
        if x.get("flow_id"):
            flows.append(x["flow_id"])
        for v in x.values():
            walk(v)
    elif isinstance(x, list):
        for v in x:
            walk(v)
walk(d)
print(placement)
for f in dict.fromkeys(flows):
    print(f)
PY
PLACEMENT="$(sed -n 1p "$RAW/ids.txt")"
i=0
while read -r FLOW; do
  i=$((i+1))
  call "funnel_$i" analytics funnel --app "$LUMEN_APP_ID" --date-from "$START" --date-to "$TODAY" \
    --filter "flow_id=$FLOW" --filter "placement_id=$PLACEMENT" --group-by store_product_id
  cp "$RAW/funnel_$i.json" "$OUT/funnel_arm_$i.json"
  echo "$FLOW" >>"$RAW/arm_order.txt"
done < <(sed -n '2,$p' "$RAW/ids.txt")

call conversion analytics conversion --app "$LUMEN_APP_ID" --conversion trial-paid --group-by store_product_id \
  --date-from 2026-07-01 --date-to "$TODAY"
cp "$RAW/conversion.json" "$OUT/conversion_trial_paid.json"
echo "recorded $i funnel arms"

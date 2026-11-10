#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:?usage: submit_agentos_scheduler_request_https.sh <action> <source_commit> [key=value ...]}"
SOURCE_COMMIT="${2:-}"
shift 2 || true

BASE="${AGENTOS_SCHEDULER_BASE:-https://studio.milkcat.org/dashboard/api/agentos}"
TOKEN="${AGENTOS_CONTROLLER_TOKEN:-}"
WAIT_SECONDS="${AGENTOS_SCHEDULER_WAIT_SECONDS:-300}"

[ -n "$TOKEN" ] || { echo "AGENTOS_CONTROLLER_TOKEN is required" >&2; exit 2; }

BODY="$(python3 - "$ACTION" "$SOURCE_COMMIT" "$@" <<'PY'
import json, re, sys
action=sys.argv[1]
source_commit=sys.argv[2]
params={}
if source_commit:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise SystemExit("source_commit must be exact lowercase 40-hex SHA")
    params["source_commit"]=source_commit
for raw in sys.argv[3:]:
    if "=" not in raw:
        raise SystemExit("extra params must be key=value")
    k,v=raw.split("=",1)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",k):
        raise SystemExit("invalid param key")
    params[k]=v
print(json.dumps({"schema":"agentos.scheduler-submit/v1","action":action,"params":params},separators=(",",":")))
PY
)"

SUBMIT="$(mktemp)"
trap 'rm -f "$SUBMIT"' EXIT
CODE="$(curl -sS -o "$SUBMIT" -w '%{http_code}' --max-time 15   -H "Authorization: Bearer $TOKEN"   -H 'Content-Type: application/json'   -d "$BODY" "$BASE/v1/controller/scheduler/submit")"
cat "$SUBMIT"
echo
[ "$CODE" = 202 ] || { echo "scheduler_submit_http=$CODE" >&2; exit 3; }

REQUEST_ID="$(python3 - "$SUBMIT" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("ok") is True,d
print(d["request_id"])
PY
)"
echo "scheduler_request_id=$REQUEST_ID"

deadline=$((SECONDS + WAIT_SECONDS))
while [ "$SECONDS" -lt "$deadline" ]; do
  STATUS="$(mktemp)"
  CODE="$(curl -sS -o "$STATUS" -w '%{http_code}' --max-time 15     -H "Authorization: Bearer $TOKEN"     "$BASE/v1/controller/scheduler/requests/$REQUEST_ID" || true)"
  if [ "$CODE" = 200 ]; then
    STATE="$(python3 - "$STATUS" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
print(d.get("state") or "unknown")
PY
)"
    if [ "$STATE" = completed ]; then
      cat "$STATUS"; echo
      python3 - "$STATUS" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
r=d.get("receipt") or {}
raise SystemExit(0 if r.get("ok") is True else 4)
PY
      rm -f "$STATUS"
      echo "scheduler_request=PASS"
      exit 0
    fi
  fi
  rm -f "$STATUS"
  sleep 2
done

echo "scheduler_request_timeout=$REQUEST_ID" >&2
exit 5

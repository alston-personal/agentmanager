#!/usr/bin/env bash
set -euo pipefail

CAPABILITY="${1:?usage: agentos_dispatch.sh <capability> <operation> <source_commit> [key=value ...]}"
OPERATION="${2:?operation is required}"
SOURCE_COMMIT="${3:?source_commit is required}"
shift 3 || true

BASE="${AGENTOS_RUNNER_WINDOW_BASE:-https://studio.milkcat.org/dashboard/api/agentos}"
TOKEN="${AGENTOS_CONTROLLER_TOKEN:-}"
WAIT_SECONDS="${AGENTOS_DISPATCH_WAIT_SECONDS:-300}"

[ -n "$TOKEN" ] || { echo "AGENTOS_CONTROLLER_TOKEN is required" >&2; exit 2; }

BODY="$(python3 - "$CAPABILITY" "$OPERATION" "$SOURCE_COMMIT" "$@" <<'PY'
import json,re,sys
capability,operation,source_commit=sys.argv[1:4]
if not re.fullmatch(r"[0-9a-f]{40}",source_commit):
    raise SystemExit("source_commit must be exact lowercase 40-hex SHA")
payload={}
for raw in sys.argv[4:]:
    if "=" not in raw:
        raise SystemExit("extra payload must be key=value")
    k,v=raw.split("=",1)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",k):
        raise SystemExit("invalid payload key")
    payload[k]=v
print(json.dumps({
    "schema":"agentos.runner-window-dispatch/v1",
    "capability":capability,
    "operation":operation,
    "source_commit":source_commit,
    "payload":payload,
},separators=(",",":")))
PY
)"

SUBMIT="$(mktemp)"
trap 'rm -f "$SUBMIT"' EXIT
CODE="$(curl -sS -o "$SUBMIT" -w '%{http_code}' --max-time 15   -H "Authorization: Bearer $TOKEN"   -H 'Content-Type: application/json'   -d "$BODY" "$BASE/v1/dispatch")"
cat "$SUBMIT"; echo
[ "$CODE" = 202 ] || { echo "runner_window_submit_http=$CODE" >&2; exit 3; }

REQUEST_ID="$(python3 - "$SUBMIT" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("ok") is True,d
assert (d.get("dispatch") or {}).get("schema")=="agentos.runner-window-plan/v1",d
print(d["request_id"])
PY
)"
echo "runner_window_request_id=$REQUEST_ID"

deadline=$((SECONDS + WAIT_SECONDS))
while [ "$SECONDS" -lt "$deadline" ]; do
  STATUS="$(mktemp)"
  CODE="$(curl -sS -o "$STATUS" -w '%{http_code}' --max-time 15     -H "Authorization: Bearer $TOKEN"     "$BASE/v1/dispatch/requests/$REQUEST_ID" || true)"
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
      echo "runner_window_dispatch=PASS"
      exit 0
    fi
  fi
  rm -f "$STATUS"
  sleep 2
done

echo "runner_window_dispatch_timeout=$REQUEST_ID" >&2
exit 5

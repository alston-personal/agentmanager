#!/usr/bin/env bash
set -euo pipefail

SERVICE_SHA="$1"
DIR=/home/ubuntu/vendor-reputation-service
SECRET=/home/ubuntu/agent-data/secrets/vendor-reputation.env
cd "$DIR"

git fetch --depth=1 origin "$SERVICE_SHA" >/dev/null 2>&1
git checkout --detach "$SERVICE_SHA" >/dev/null 2>&1

set -a
. "$SECRET"
set +a
: "${VENDOR_DB_PASSWORD:?VENDOR_DB_PASSWORD is required}"

redact() {
  local value="$1"
  if [ -n "${VENDOR_DB_PASSWORD:-}" ]; then
    value="${value//${VENDOR_DB_PASSWORD}/[REDACTED]}"
  fi
  printf '%s' "$value"
}

docker compose up -d db >/dev/null
READY=0
for _ in $(seq 1 30); do
  if docker compose exec -T db psql -U vendor_service -d vendor_reputation -Atqc 'select 1' </dev/null >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then
  printf '%s\n' '{"schema":"milkcat.vendor-monitored-source-sync/v1","ok":false,"failed_stage":"db-ready","sources":0,"discovered":0,"inserted":0,"updated":0,"unchanged":0,"errors":1,"raw_text_emitted":false,"login_bypass_used":false,"anti_bot_bypass_used":false,"reviews_published":false,"core_modified":false}'
  exit 1
fi

for migration in sql/*.sql; do
  docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < "$migration" >/dev/null
done

docker compose --profile tools build threads-sync >/dev/null
OUT=$(mktemp)
ERR=$(mktemp)
trap 'rm -f "$OUT" "$ERR"' EXIT
set +e
docker compose --profile tools run --rm -T threads-sync </dev/null >"$OUT" 2>"$ERR"
RC=$?
set -e

if [ ! -s "$OUT" ]; then
  TAIL=$(tail -c 1000 "$ERR" 2>/dev/null | tr '\n\r\t' '   ' || true)
  TAIL=$(redact "$TAIL")
  python3 - "$RC" "$TAIL" <<'PY'
import json,sys
print(json.dumps({
  'schema':'milkcat.vendor-monitored-source-sync/v1',
  'ok':False,
  'failed_stage':'browser-sync',
  'worker_exit_code':int(sys.argv[1]),
  'sources':0,'discovered':0,'inserted':0,'updated':0,'unchanged':0,'errors':1,
  'sanitized_error_tail':sys.argv[2],
  'raw_text_emitted':False,'login_bypass_used':False,'anti_bot_bypass_used':False,
  'reviews_published':False,'core_modified':False
},ensure_ascii=False))
PY
  exit "$RC"
fi

python3 -m json.tool "$OUT" >/dev/null
cat "$OUT"
exit "$RC"

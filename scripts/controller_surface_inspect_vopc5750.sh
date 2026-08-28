#!/usr/bin/env bash
set -euo pipefail
OUT=/tmp/agentos-controller-surface-inspect-vopc5750.json
code=$(curl -sS -o "$OUT" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"schema":"agentos.controller-dispatch/v0.1","node_id":"vopc5750","action":"agent.surface.inspect","payload":{}}' \
  http://127.0.0.1:8780/v1/controller/dispatch)
echo "controller_dispatch_http_code=$code"
cat "$OUT"
if [ "$code" = 404 ]; then
  echo 'controller_dispatch=FAIL_NOT_FOUND' >&2
  exit 44
fi
python3 - "$OUT" "$code" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
code=int(sys.argv[2])
assert code == 200, (code,p)
assert p.get('ok') is True,p
assert p.get('controller_entered') is True,p
assert p.get('node_id') == 'vopc5750',p
assert p.get('action') == 'agent.surface.inspect',p
assert p.get('task_id'),p
print('controller_service_entered=PASS')
print('controller_task_id='+p['task_id'])
PY

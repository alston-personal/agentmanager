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
if code == 200:
    assert p.get('ok') is True,p
    assert p.get('controller_entered') is True,p
    assert p.get('node_id') == 'vopc5750',p
    assert p.get('action') == 'agent.surface.inspect',p
    assert p.get('task_id'),p
    print('controller_service_entered=PASS')
    print('controller_dispatch_outcome=TASK_QUEUED')
    print('controller_task_id='+p['task_id'])
    raise SystemExit(0)
if code == 400:
    error=str(p.get('error') or '')
    assert 'target node does not advertise capability: agent.surface.inspect' in error,(code,p)
    # This validation is raised inside ControllerService after the live route has
    # parsed the dispatch and resolved the target node.  It is therefore valid
    # Core route-entry evidence; capability readiness belongs to the Node thread.
    print('controller_service_entered=PASS')
    print('controller_dispatch_outcome=NODE_CAPABILITY_NOT_ADVERTISED')
    raise SystemExit(0)
raise AssertionError((code,p))
PY

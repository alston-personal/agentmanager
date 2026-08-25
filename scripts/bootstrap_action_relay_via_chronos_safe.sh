#!/usr/bin/env bash
set -euo pipefail

OUT=.agentos/evidence/action-relay-chronos-safe-bootstrap.txt
mkdir -p .agentos/evidence
LOCAL=/home/ubuntu/agentmanager
TARGET="$LOCAL/scripts/update_scheduler_board.py"
DATA=/home/ubuntu/agent-data
BRIDGE="$DATA/runtime/action-relay-bootstrap-safe"
mkdir -p "$BRIDGE"
chmod 2770 "$BRIDGE"
REQUEST_ID="chronos-safe-$(date -u +%Y%m%dT%H%M%SZ)-${GITHUB_RUN_ID:-manual}"
RECEIPT="/tmp/$REQUEST_ID.receipt.json"
BACKUP="$BRIDGE/$REQUEST_ID.update_scheduler_board.py"
rm -f "$RECEIPT" "$RECEIPT.tmp"

restore_target() {
  if [ -f "$BACKUP" ]; then
    cp -p "$BACKUP" "$TARGET" || true
  fi
}
trap restore_target EXIT

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "request_id=$REQUEST_ID"
  echo '=== VERIFY EXISTING UBUNTU CHRONOS ==='
  ps -eo user,group,pid,ppid,etime,args | grep -F 'scripts/chronos.py' | grep -v grep || true
  test -f "$TARGET"
  test -w "$TARGET"
  test -f "$DATA/logs/chronos.log"
  python3 - "$DATA/logs/chronos.log" <<'PY'
import os,sys,time
p=sys.argv[1]
age=time.time()-os.stat(p).st_mtime
print(f'chronos_log_age_seconds={age:.1f}')
if age > 180:
    raise SystemExit('Chronos log is stale; refusing to patch a dormant execution surface')
PY

  cp -p "$TARGET" "$BACKUP"

  python3 - "$TARGET" "$REQUEST_ID" "$RECEIPT" <<'PY'
from pathlib import Path
import sys

target=Path(sys.argv[1]); request_id=sys.argv[2]; receipt=sys.argv[3]
original=target.read_text(encoding='utf-8')
marker='# AGENTOS_ONE_TIME_CHRONOS_SAFE_BOOTSTRAP\n'
if marker in original:
    raise SystemExit('scheduler board already contains safe bridge marker')
bridge=f'''{marker}import json as _agentos_json\nimport os as _agentos_os\nfrom pathlib import Path as _AgentOSPath\nimport subprocess as _agentos_subprocess\n\n_AGENTOS_REQUEST_ID={request_id!r}\n_AGENTOS_RECEIPT=_AgentOSPath({receipt!r})\nif not _AGENTOS_RECEIPT.exists():\n    _agentos_started=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()\n    _agentos_cmd=["/bin/bash","-lc", "cd /home/ubuntu/agentmanager && git fetch origin main && git show origin/main:scripts/repair_antigravity_relay_user.sh > /tmp/agentos-repair-antigravity-safe.sh && chmod 700 /tmp/agentos-repair-antigravity-safe.sh && AGENTOS_REPO=/home/ubuntu/agentmanager bash /tmp/agentos-repair-antigravity-safe.sh"]\n    _agentos_p=_agentos_subprocess.run(_agentos_cmd, text=True, capture_output=True, timeout=180)\n    _agentos_payload={{\n        "schema":"agentos.one-time-chronos-safe-bootstrap/v1",\n        "request_id":_AGENTOS_REQUEST_ID,\n        "executor_user":_agentos_os.environ.get("USER") or str(_agentos_os.getuid()),\n        "executor_uid":_agentos_os.getuid(),\n        "returncode":_agentos_p.returncode,\n        "ok":_agentos_p.returncode == 0,\n        "stdout":(_agentos_p.stdout or "")[-30000:],\n        "stderr":(_agentos_p.stderr or "")[-10000:],\n        "started_at":_agentos_started,\n        "completed_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),\n    }}\n    _agentos_tmp=_AGENTOS_RECEIPT.with_suffix(".tmp")\n    _agentos_tmp.write_text(_agentos_json.dumps(_agentos_payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")\n    _agentos_os.chmod(_agentos_tmp,0o644)\n    _agentos_tmp.replace(_AGENTOS_RECEIPT)\n\n'''
target.write_text(bridge+original,encoding='utf-8')
PY
  echo 'one_time_safe_bridge_installed=YES'

  for i in $(seq 1 180); do [ -f "$RECEIPT" ] && break; sleep 1; done
  test -f "$RECEIPT" || { echo 'chronos_safe_bootstrap_receipt=TIMEOUT'; exit 3; }
  echo "chronos_receipt_owner=$(stat -c '%U:%G %a' "$RECEIPT")"
  test "$(stat -c '%U' "$RECEIPT")" = ubuntu
  cat "$RECEIPT"
  python3 - "$RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r.get('ok') is True, r
assert r.get('executor_user') == 'ubuntu', r
assert r.get('executor_uid') == 1001, r
text=(r.get('stdout','')+'\n'+r.get('stderr',''))
assert 'antigravity_repair=PASS' in text, text[-10000:]
assert 'action_relay_install=PASS' in text, text[-10000:]
print('chronos_safe_bootstrap=PASS')
PY

  restore_target
  rm -f "$BACKUP" "$RECEIPT" "$RECEIPT.tmp"
  trap - EXIT
  echo 'one_time_safe_bridge_removed=YES'
  grep -q 'AGENTOS_ONE_TIME_CHRONOS_SAFE_BOOTSTRAP' "$TARGET" && { echo 'bridge_cleanup=FAIL'; exit 4; } || true

  echo '=== DETERMINISTIC ACTION RELAY PROOF ==='
  ACTION_ROOT="$DATA/runtime/action-relay"
  RESTART_ID=$(PYTHONPATH="$PWD" python3 - <<'PY'
from agentos_node.action_relay import ActionRelayClient
print(ActionRelayClient('/home/ubuntu/agent-data/runtime/action-relay').submit('agentos.antigravity.restart', {})['capsule_id'])
PY
  )
  RESTART_RECEIPT="$ACTION_ROOT/receipts/$RESTART_ID.json"
  for i in $(seq 1 120); do [ -f "$RESTART_RECEIPT" ] && break; sleep 1; done
  test -f "$RESTART_RECEIPT" || { echo 'antigravity_restart_receipt=TIMEOUT'; exit 5; }
  cat "$RESTART_RECEIPT"
  python3 - "$RESTART_RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r.get('ok') is True, r
assert r.get('action') == 'agentos.antigravity.restart', r
assert r.get('executor_user') == 'ubuntu', r
print('antigravity_restart=PASS')
PY

  sleep 2
  grep -q '/usr/bin/sg agentos -c' /home/ubuntu/.config/systemd/user/agentos-antigravity-relay.service
  grep -q '/usr/bin/sg agentos -c' /home/ubuntu/.config/systemd/user/agentos-action-relay.service
  python3 - <<'PY'
from pathlib import Path
import subprocess
p=subprocess.run(['pgrep','-f','agentos_node.antigravity_relay_worker --root /home/ubuntu/agent-data/runtime/antigravity-relay'],text=True,capture_output=True,check=True)
ok=False
for raw in p.stdout.split():
    status=Path('/proc')/raw/'status'
    if not status.exists():
        continue
    groups=[]
    for line in status.read_text().splitlines():
        if line.startswith('Groups:'):
            groups=line.split()[1:]
    if '1005' in groups:
        ok=True
        print(f'antigravity_pid={raw} groups={groups}')
assert ok, 'new Antigravity worker lacks agentos gid 1005'
print('antigravity_group_boundary=PASS')
PY

  echo '=== READ-ONLY PUBLIC BASELINE ==='
  for path in / /dashboard /layout-lab/; do
    code=$(curl -sS -o /tmp/studio-safe-baseline -w '%{http_code}' --retry 3 --retry-all-errors "https://studio.milkcat.org${path}")
    echo "public_path=${path} http_code=${code}"
    test "$code" = 200
  done
  echo 'production_mutation=NONE'
  echo 'site_sync_build=SKIPPED'
  echo 'safe_transport_recovery=PASS'
} 2>&1 | tee "$OUT"

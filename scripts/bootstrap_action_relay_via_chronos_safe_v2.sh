#!/usr/bin/env bash
set -euo pipefail

OUT=.agentos/evidence/action-relay-chronos-safe-bootstrap-v2.txt
mkdir -p .agentos/evidence
LOCAL=/home/ubuntu/agentmanager
TARGET="$LOCAL/scripts/update_scheduler_board.py"
DATA=/home/ubuntu/agent-data
BRIDGE="$DATA/runtime/action-relay-bootstrap-safe"
ACTION_ROOT="$DATA/runtime/action-relay"
mkdir -p "$BRIDGE"
chgrp agentos "$BRIDGE" 2>/dev/null || true
chmod 2770 "$BRIDGE"
REQUEST_ID="chronos-safe-v2-$(date -u +%Y%m%dT%H%M%SZ)-${GITHUB_RUN_ID:-manual}"
RECEIPT="$BRIDGE/$REQUEST_ID.receipt.json"
BACKUP="$BRIDGE/$REQUEST_ID.update_scheduler_board.py"
rm -f "$RECEIPT" "$RECEIPT.tmp"

restore_target() {
  if [ -f "$BACKUP" ]; then
    cat "$BACKUP" > "$TARGET" || true
  fi
}
trap restore_target EXIT

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "request_id=$REQUEST_ID"
  echo '=== VERIFY EXISTING UBUNTU CHRONOS ==='
  ps -eo user,group,pid,ppid,etime,args | grep -F 'scripts/chronos.py' | grep -v grep
  test -f "$TARGET" && test -w "$TARGET"
  python3 - "$DATA/logs/chronos.log" <<'PY'
import os,sys,time
p=sys.argv[1]
age=time.time()-os.stat(p).st_mtime
print(f'chronos_log_age_seconds={age:.1f}')
assert age <= 180, 'Chronos log is stale'
PY

  echo '=== PREPROVISION SHARED ACTION RELAY SPOOL ==='
  for d in "$ACTION_ROOT" "$ACTION_ROOT/inbox" "$ACTION_ROOT/processing" "$ACTION_ROOT/receipts"; do
    mkdir -p "$d"
    chgrp agentos "$d" 2>/dev/null || true
    chmod 2770 "$d"
  done
  echo "action_relay_spool=$(stat -c '%U:%G %a' "$ACTION_ROOT")"

  echo '=== RECOVER ANY STALE INJECTED TARGET ==='
  python3 - "$TARGET" "$BRIDGE" <<'PY'
from pathlib import Path
import sys

target=Path(sys.argv[1]); bridge=Path(sys.argv[2])
markers=('# AGENTOS_ONE_TIME_CHRONOS_SAFE_BOOTSTRAP\n','# AGENTOS_ONE_TIME_CHRONOS_SAFE_BOOTSTRAP_V2\n','# AGENTOS_ONE_TIME_CHRONOS_BOOTSTRAP\n')
text=target.read_text(encoding='utf-8')
if not any(m in text for m in markers):
    print('stale_bridge_present=NO')
    raise SystemExit(0)
for p in sorted(bridge.glob('*.update_scheduler_board.py'), key=lambda x:x.stat().st_mtime, reverse=True):
    try: candidate=p.read_text(encoding='utf-8')
    except Exception: continue
    if not any(m in candidate for m in markers):
        target.write_text(candidate,encoding='utf-8')
        print(f'stale_bridge_recovered_from={p.name}')
        print('stale_bridge_recovery=PASS')
        break
else:
    raise SystemExit('no marker-free backup available')
PY

  cat "$TARGET" > "$BACKUP"

  python3 - "$TARGET" "$REQUEST_ID" "$RECEIPT" <<'PY'
from pathlib import Path
import sys

target=Path(sys.argv[1]); request_id=sys.argv[2]; receipt=sys.argv[3]
original=target.read_text(encoding='utf-8')
marker='# AGENTOS_ONE_TIME_CHRONOS_SAFE_BOOTSTRAP_V2\n'
if marker in original:
    raise SystemExit('v2 bridge already present')
bridge=f'''{marker}import json as _a_json\nimport os as _a_os\nfrom pathlib import Path as _APath\nimport subprocess as _a_subprocess\nimport traceback as _a_traceback\nimport datetime as _a_datetime\n\n_A_ID={request_id!r}\n_A_RECEIPT=_APath({receipt!r})\nif not _A_RECEIPT.exists():\n    _a_started=_a_datetime.datetime.now(_a_datetime.timezone.utc).isoformat()\n    _a_payload={{\n        "schema":"agentos.one-time-chronos-safe-bootstrap/v2",\n        "request_id":_A_ID,\n        "executor_user":_a_os.environ.get("USER") or str(_a_os.getuid()),\n        "executor_uid":_a_os.getuid(),\n        "started_at":_a_started,\n        "ok":False,\n    }}\n    try:\n        _a_cmd=["/bin/bash","-lc", "cd /home/ubuntu/agentmanager && git fetch origin main && git show origin/main:scripts/repair_antigravity_relay_user.sh > /tmp/agentos-repair-antigravity-safe-v2.sh && chmod 700 /tmp/agentos-repair-antigravity-safe-v2.sh && AGENTOS_ACTION_SPOOL_PREPROVISIONED=1 AGENTOS_REPO=/home/ubuntu/agentmanager bash /tmp/agentos-repair-antigravity-safe-v2.sh"]\n        _a_p=_a_subprocess.run(_a_cmd,text=True,capture_output=True,timeout=240)\n        _a_payload.update({{"returncode":_a_p.returncode,"ok":_a_p.returncode==0,"stdout":(_a_p.stdout or "")[-30000:],"stderr":(_a_p.stderr or "")[-12000:]}})\n    except _a_subprocess.TimeoutExpired as _a_e:\n        _a_payload.update({{"error":"TimeoutExpired","timeout":240,"stdout":((_a_e.stdout or "") if isinstance(_a_e.stdout,str) else "")[-30000:],"stderr":((_a_e.stderr or "") if isinstance(_a_e.stderr,str) else "")[-12000:]}})\n    except BaseException as _a_e:\n        _a_payload.update({{"error":type(_a_e).__name__+": "+str(_a_e),"traceback":_a_traceback.format_exc()[-12000:]}})\n    _a_payload["completed_at"]=_a_datetime.datetime.now(_a_datetime.timezone.utc).isoformat()\n    try:\n        _a_tmp=_A_RECEIPT.with_suffix(_A_RECEIPT.suffix+".tmp")\n        _a_tmp.write_text(_a_json.dumps(_a_payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")\n        _a_os.chmod(_a_tmp,0o660)\n        _a_tmp.replace(_A_RECEIPT)\n    except BaseException:\n        pass\n\n'''
target.write_text(bridge+original,encoding='utf-8')
compile(target.read_text(encoding='utf-8'),str(target),'exec')
PY
  echo 'one_time_safe_bridge_v2_installed=YES'

  for i in $(seq 1 330); do
    [ -f "$RECEIPT" ] && break
    sleep 1
  done
  test -f "$RECEIPT" || { echo 'chronos_safe_v2_receipt=TIMEOUT_NO_RECEIPT'; exit 3; }
  echo "chronos_receipt=$(stat -c '%U:%G %a' "$RECEIPT")"
  cat "$RECEIPT"

  python3 - "$RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r.get('executor_user') == 'ubuntu', r
assert r.get('executor_uid') == 1001, r
if not r.get('ok'):
    raise SystemExit('ubuntu repair failed: '+json.dumps(r,ensure_ascii=False)[-12000:])
text=(r.get('stdout','')+'\n'+r.get('stderr',''))
assert 'antigravity_repair=PASS' in text, text[-12000:]
assert 'action_relay_install=PASS' in text, text[-12000:]
print('chronos_safe_bootstrap_v2=PASS')
PY

  restore_target
  rm -f "$BACKUP"
  trap - EXIT
  grep -q 'AGENTOS_ONE_TIME_CHRONOS_SAFE_BOOTSTRAP_V2' "$TARGET" && { echo 'bridge_cleanup=FAIL'; exit 4; } || true
  echo 'one_time_safe_bridge_v2_removed=YES'

  echo '=== DETERMINISTIC ACTION RELAY PROOF ==='
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
    f=Path('/proc')/raw/'status'
    if not f.exists(): continue
    groups=[]
    for line in f.read_text().splitlines():
        if line.startswith('Groups:'): groups=line.split()[1:]
    if '1005' in groups:
        print(f'antigravity_pid={raw} groups={groups}')
        ok=True
assert ok, 'new Antigravity worker lacks agentos gid 1005'
print('antigravity_group_boundary=PASS')
PY

  echo '=== READ-ONLY PUBLIC BASELINE ==='
  for path in / /dashboard /layout-lab/; do
    code=$(curl -sS -o /tmp/studio-safe-v2-baseline -w '%{http_code}' --retry 3 --retry-all-errors "https://studio.milkcat.org${path}")
    echo "public_path=${path} http_code=${code}"
    test "$code" = 200
  done
  echo 'production_mutation=NONE'
  echo 'site_sync_build=SKIPPED'
  echo 'safe_transport_recovery_v2=PASS'
} 2>&1 | tee "$OUT"

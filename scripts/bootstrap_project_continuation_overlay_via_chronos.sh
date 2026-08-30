#!/usr/bin/env bash
set -euo pipefail

INSTALLER_COMMIT="${1:?exact installer commit required}"
[[ "$INSTALLER_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid installer commit' >&2; exit 2; }

LOCAL=/home/ubuntu/agentmanager
TARGET="$LOCAL/scripts/update_scheduler_board.py"
DATA=/home/ubuntu/agent-data
BRIDGE="$DATA/runtime/project-continuation-overlay-bootstrap"
REQUEST_ID="continuation-overlay-$(date -u +%Y%m%dT%H%M%SZ)-${GITHUB_RUN_ID:-manual}"
RECEIPT="$BRIDGE/$REQUEST_ID.receipt.json"
BACKUP="$BRIDGE/$REQUEST_ID.update_scheduler_board.py"
mkdir -p "$BRIDGE"
chgrp agentos "$BRIDGE" 2>/dev/null || true
chmod 2770 "$BRIDGE"
rm -f "$RECEIPT" "$RECEIPT.tmp"

restore_target() {
  if [ -f "$BACKUP" ]; then cat "$BACKUP" > "$TARGET" || true; fi
}
trap restore_target EXIT

test -f "$TARGET" && test -w "$TARGET"
python3 - "$DATA/logs/chronos.log" <<'PY'
import os,sys,time
p=sys.argv[1]; age=time.time()-os.stat(p).st_mtime
print(f'chronos_log_age_seconds={age:.1f}')
assert age <= 180, 'Chronos log is stale'
PY
ps -eo user,group,pid,ppid,lstart,etime,args | grep -F 'scripts/chronos.py' | grep -v grep

echo '=== live Chronos triggers before bridge ==='
tail -n 1500 "$DATA/logs/chronos.log" | grep -E "Loaded [0-9]+ scheduled tasks|swarm-board-refresh|update_scheduler_board.py|\[Trigger\]" | tail -n 200 || true

cat "$TARGET" > "$BACKUP"
python3 - "$TARGET" "$REQUEST_ID" "$RECEIPT" "$INSTALLER_COMMIT" <<'PY'
from pathlib import Path
import sys

target=Path(sys.argv[1]); request_id=sys.argv[2]; receipt=sys.argv[3]; installer_commit=sys.argv[4]
original=target.read_text(encoding='utf-8')
marker='# AGENTOS_ONE_TIME_PROJECT_CONTINUATION_OVERLAY_V1\n'
if marker in original: raise SystemExit('continuation overlay bridge already present')
bridge=f'''{marker}import datetime as _pc_datetime\nimport json as _pc_json\nimport os as _pc_os\nfrom pathlib import Path as _PCPath\nimport subprocess as _pc_subprocess\nimport traceback as _pc_traceback\n\n_PC_ID={request_id!r}\n_PC_RECEIPT=_PCPath({receipt!r})\n_PC_INSTALLER_COMMIT={installer_commit!r}\nif not _PC_RECEIPT.exists():\n    _pc_payload={{\n        "schema":"agentos.one-time-project-continuation-overlay-bootstrap/v1",\n        "request_id":_PC_ID,\n        "installer_commit":_PC_INSTALLER_COMMIT,\n        "executor_user":_pc_os.environ.get("USER") or str(_pc_os.getuid()),\n        "executor_uid":_pc_os.getuid(),\n        "started_at":_pc_datetime.datetime.now(_pc_datetime.timezone.utc).isoformat(),\n        "ok":False,\n    }}\n    try:\n        _pc_fetch=_pc_subprocess.run(["git","-C","/home/ubuntu/agentmanager","fetch","origin",_PC_INSTALLER_COMMIT],text=True,capture_output=True,timeout=120,check=False)\n        if _pc_fetch.returncode != 0:\n            raise RuntimeError("installer fetch failed: "+(_pc_fetch.stderr or "")[-4000:])\n        _pc_show=_pc_subprocess.run(["git","-C","/home/ubuntu/agentmanager","show",_PC_INSTALLER_COMMIT+":scripts/install_project_continuation_overlay.py"],capture_output=True,timeout=30,check=False)\n        if _pc_show.returncode != 0:\n            raise RuntimeError("installer git-show failed: "+_pc_show.stderr.decode("utf-8","replace")[-4000:])\n        _pc_installer=_PCPath("/tmp")/("agentos-project-continuation-overlay-"+_PC_ID+".py")\n        _pc_installer.write_bytes(_pc_show.stdout)\n        _pc_os.chmod(_pc_installer,0o700)\n        _pc_run=_pc_subprocess.run(["/usr/bin/python3",str(_pc_installer)],text=True,capture_output=True,timeout=180,check=False)\n        _pc_payload.update({{\n            "returncode":_pc_run.returncode,\n            "ok":_pc_run.returncode==0,\n            "stdout":(_pc_run.stdout or "")[-30000:],\n            "stderr":(_pc_run.stderr or "")[-12000:],\n        }})\n    except BaseException as _pc_e:\n        _pc_payload.update({{"error":type(_pc_e).__name__+": "+str(_pc_e),"traceback":_pc_traceback.format_exc()[-12000:]}})\n    _pc_payload["completed_at"]=_pc_datetime.datetime.now(_pc_datetime.timezone.utc).isoformat()\n    try:\n        _pc_tmp=_PC_RECEIPT.with_suffix(_PC_RECEIPT.suffix+".tmp")\n        _pc_tmp.write_text(_pc_json.dumps(_pc_payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")\n        _pc_os.chmod(_pc_tmp,0o660)\n        _pc_tmp.replace(_PC_RECEIPT)\n    except BaseException:\n        pass\n\n'''
target.write_text(bridge+original,encoding='utf-8')
compile(target.read_text(encoding='utf-8'),str(target),'exec')
PY

echo "continuation_overlay_bridge_installed=YES request_id=$REQUEST_ID"
for i in $(seq 1 90); do [ -f "$RECEIPT" ] && break; sleep 1; done
if [ ! -f "$RECEIPT" ]; then
  echo 'continuation_overlay_receipt=TIMEOUT'
  echo '=== live Chronos triggers during bridge window ==='
  tail -n 2000 "$DATA/logs/chronos.log" | grep -E "Loaded [0-9]+ scheduled tasks|swarm-board-refresh|update_scheduler_board.py|\[Trigger\]" | tail -n 260 || true
  echo '=== update_scheduler_board process evidence ==='
  ps -eo user,group,pid,ppid,lstart,etime,args | grep -F 'update_scheduler_board.py' | grep -v grep || true
  exit 3
fi
cat "$RECEIPT"

python3 - "$RECEIPT" "$INSTALLER_COMMIT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding='utf-8'))
assert r.get('executor_user')=='ubuntu',r
assert r.get('executor_uid')==1001,r
assert r.get('installer_commit')==sys.argv[2],r
assert r.get('ok') is True,r
text=(r.get('stdout') or '')+'\n'+(r.get('stderr') or '')
assert 'action_relay_continuation_overlay=PASS' in text,text[-12000:]
lines=[x for x in (r.get('stdout') or '').splitlines() if x.startswith('{')]
assert lines,r
inner=json.loads(lines[-1])
assert inner.get('ok') is True,inner
assert inner.get('executor_user')=='ubuntu',inner
assert inner.get('live_core_generation')==6,inner
assert inner.get('live_core_commit')=='f842bee2cf7c24fc3bf7424bd121994562e829cd',inner
assert inner.get('overlay_source_commit')=='f842bee2cf7c24fc3bf7424bd121994562e829cd',inner
assert inner.get('required_governance_actions_preserved') is True,inner
assert inner.get('publisher_action')=='agentos.project.publish_continuation',inner
print('chronos_continuation_overlay=PASS')
PY

restore_target
rm -f "$BACKUP"
trap - EXIT
if grep -q 'AGENTOS_ONE_TIME_PROJECT_CONTINUATION_OVERLAY_V1' "$TARGET"; then
  echo 'continuation_overlay_bridge_cleanup=FAIL' >&2; exit 4
fi
echo 'continuation_overlay_bridge_cleanup=PASS'
cp "$RECEIPT" /tmp/project-continuation-overlay-bootstrap-receipt.json

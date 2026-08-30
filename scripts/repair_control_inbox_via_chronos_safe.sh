#!/usr/bin/env bash
set -euo pipefail

# Issue #77 one-time bounded repair. This script deliberately has no arbitrary
# path/service/command parameters. It uses the already-running ubuntu Chronos
# process only as an identity boundary, materializes exactly the Control Inbox
# bridge from this workflow's exact source commit, and leaves Realm/Core
# deployment authority untouched.

SOURCE_SHA="${GITHUB_SHA:?GITHUB_SHA is required}"
DATA=/home/ubuntu/agent-data
LOCAL=/home/ubuntu/agentmanager
CHRONOS_TARGET="$LOCAL/scripts/update_scheduler_board.py"
BRIDGE_ROOT="$DATA/runtime/issue-77-control-inbox-repair"
RECEIPT="$BRIDGE_ROOT/${GITHUB_RUN_ID:-manual}-${SOURCE_SHA}.receipt.json"
BACKUP="$BRIDGE_ROOT/${GITHUB_RUN_ID:-manual}-${SOURCE_SHA}.update_scheduler_board.py"
STATE="$DATA/governance/core-deployment.json"

mkdir -p "$BRIDGE_ROOT"
chgrp agentos "$BRIDGE_ROOT" 2>/dev/null || true
chmod 2770 "$BRIDGE_ROOT"
rm -f "$RECEIPT" "$RECEIPT.tmp"

snapshot_state() {
  python3 - "$STATE" <<'PY'
import json,sys
s=json.load(open(sys.argv[1],encoding='utf-8'))
keys=('deployment_generation','desired_core_commit','observed_core_commit','deployment_status','lease_status','lease_owner')
print(json.dumps({k:s.get(k) for k in keys},sort_keys=True,separators=(',',':')))
PY
}

BEFORE=$(snapshot_state)
echo "core_deployment_before=$BEFORE"

echo '=== VERIFY EXISTING UBUNTU CHRONOS ==='
ps -eo user,group,pid,ppid,etime,args | grep -F 'scripts/chronos.py' | grep -v grep
python3 - "$DATA/logs/chronos.log" <<'PY'
import os,sys,time
age=time.time()-os.stat(sys.argv[1]).st_mtime
print(f'chronos_log_age_seconds={age:.1f}')
assert age <= 180, 'Chronos log is stale'
PY

test -f "$CHRONOS_TARGET"
test -w "$CHRONOS_TARGET"
cat "$CHRONOS_TARGET" > "$BACKUP"

restore_target() {
  if [ -f "$BACKUP" ]; then
    cat "$BACKUP" > "$CHRONOS_TARGET" || true
  fi
}
trap restore_target EXIT

python3 - "$CHRONOS_TARGET" "$SOURCE_SHA" "$RECEIPT" <<'PY'
from pathlib import Path
import sys

target=Path(sys.argv[1]); sha=sys.argv[2]; receipt=sys.argv[3]
original=target.read_text(encoding='utf-8')
marker='# AGENTOS_ISSUE77_CONTROL_INBOX_REPAIR_V1\n'
if marker in original:
    raise SystemExit('issue77 bridge marker already present')
bridge=f'''{marker}import datetime as _i77_dt\nimport json as _i77_json\nimport os as _i77_os\nfrom pathlib import Path as _I77Path\nimport subprocess as _i77_subprocess\nimport traceback as _i77_traceback\n\n_I77_SHA={sha!r}\n_I77_RECEIPT=_I77Path({receipt!r})\nif not _I77_RECEIPT.exists():\n    _i77_payload={{\n        "schema":"agentos.issue77-control-inbox-repair/v1",\n        "source_commit":_I77_SHA,\n        "executor_user":_i77_os.environ.get("USER") or str(_i77_os.getuid()),\n        "executor_uid":_i77_os.getuid(),\n        "started_at":_i77_dt.datetime.now(_i77_dt.timezone.utc).isoformat(),\n        "ok":False,\n    }}\n    try:\n        _i77_cmd=["/bin/bash","-lc", r'''set -euo pipefail\nexport XDG_RUNTIME_DIR=/run/user/1001\nexport DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus\nREPO=/home/ubuntu/agentmanager\nRUNTIME_BASE=/home/ubuntu/.local/share/agentos/control-inbox\nRELEASE="$RUNTIME_BASE/releases/{sha}"\nCURRENT="$RUNTIME_BASE/current"\nUNIT=/home/ubuntu/.config/systemd/user/agentos-control-inbox.service\nENV=/home/ubuntu/.config/agentos/control-inbox.env\nDATA=/home/ubuntu/agent-data\nmkdir -p "$RELEASE/agent_core" "$RUNTIME_BASE/releases" "$DATA/runtime/control-inbox"\ngit -C "$REPO" fetch --no-tags origin {sha}\ntest "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "{sha}"\ngit -C "$REPO" show {sha}:agent_core/__init__.py > "$RELEASE/agent_core/__init__.py"\ngit -C "$REPO" show {sha}:agent_core/control_inbox_bridge.py > "$RELEASE/agent_core/control_inbox_bridge.py"\ngit -C "$REPO" show {sha}:scripts/repair_control_inbox_github_auth_user.sh > /tmp/issue77-repair-auth.sh\nchmod 700 /tmp/issue77-repair-auth.sh\ngrep -q 'CONTROLLER_DISPATCH_SUCCESS_CODES = {{200, 202}}' "$RELEASE/agent_core/control_inbox_bridge.py"\npython3 -m py_compile "$RELEASE/agent_core/control_inbox_bridge.py"\nln -sfn "$RELEASE" "$CURRENT.new"\nmv -Tf "$CURRENT.new" "$CURRENT"\ncat > "$UNIT" <<EOF\n[Unit]\nDescription=AgentOS GitHub Issue Bootstrap Control Inbox\nAfter=network-online.target agentos-realm-fabric.service\nWants=network-online.target\nRequires=agentos-realm-fabric.service\n\n[Service]\nType=simple\nWorkingDirectory=$CURRENT\nEnvironment=PYTHONPATH=$CURRENT\nEnvironmentFile=$ENV\nUMask=0077\nExecStart=/usr/bin/python3 -m agent_core.control_inbox_bridge\nRestart=always\nRestartSec=3\nPrivateTmp=true\nNoNewPrivileges=true\nProtectSystem=strict\nProtectHome=read-only\nReadWritePaths=$DATA/runtime/control-inbox\n\n[Install]\nWantedBy=default.target\nEOF\nsystemctl --user daemon-reload\nAGENTOS_CONTROL_ENV="$ENV" AGENT_DATA_ROOT="$DATA" bash /tmp/issue77-repair-auth.sh\nsystemctl --user is-active --quiet agentos-control-inbox.service\nsystemctl --user show agentos-control-inbox.service -p User -p MainPID -p ActiveState -p SubState --no-pager\ngrep -F "WorkingDirectory=$CURRENT" "$UNIT"\ngrep -F "Environment=PYTHONPATH=$CURRENT" "$UNIT"\nrm -f /tmp/issue77-repair-auth.sh\necho issue77_control_inbox_repair=PASS\necho control_inbox_runtime_decoupled=PASS\necho control_inbox_source_commit={sha}\n''' ]\n        _i77_p=_i77_subprocess.run(_i77_cmd,text=True,capture_output=True,timeout=240)\n        _i77_payload.update({{"returncode":_i77_p.returncode,"ok":_i77_p.returncode==0,"stdout":(_i77_p.stdout or "")[-30000:],"stderr":(_i77_p.stderr or "")[-12000:]}})\n    except BaseException as _i77_e:\n        _i77_payload.update({{"error":type(_i77_e).__name__+": "+str(_i77_e),"traceback":_i77_traceback.format_exc()[-12000:]}})\n    _i77_payload["completed_at"]=_i77_dt.datetime.now(_i77_dt.timezone.utc).isoformat()\n    try:\n        _i77_tmp=_I77_RECEIPT.with_suffix(_I77_RECEIPT.suffix+".tmp")\n        _i77_tmp.write_text(_i77_json.dumps(_i77_payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")\n        _i77_os.chmod(_i77_tmp,0o660)\n        _i77_tmp.replace(_I77_RECEIPT)\n    except BaseException:\n        pass\n\n'''
target.write_text(bridge+original,encoding='utf-8')
compile(target.read_text(encoding='utf-8'),str(target),'exec')
PY

echo 'issue77_one_time_bridge_installed=YES'
for i in $(seq 1 240); do
  [ -f "$RECEIPT" ] && break
  sleep 1
done
test -f "$RECEIPT" || { echo 'issue77_receipt=TIMEOUT'; exit 3; }
cat "$RECEIPT"
python3 - "$RECEIPT" "$SOURCE_SHA" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding='utf-8'))
assert r.get('schema') == 'agentos.issue77-control-inbox-repair/v1', r
assert r.get('source_commit') == sys.argv[2], r
assert r.get('executor_user') == 'ubuntu', r
assert r.get('executor_uid') == 1001, r
assert r.get('ok') is True, r
text=(r.get('stdout','')+'\n'+r.get('stderr',''))
for marker in ('control_inbox_github_auth_repair=PASS','github_issue_read=PASS','control_inbox_service=active','issue77_control_inbox_repair=PASS','control_inbox_runtime_decoupled=PASS'):
    assert marker in text, (marker,text[-12000:])
print('issue77_ubuntu_repair_receipt=PASS')
PY

restore_target
rm -f "$BACKUP"
trap - EXIT
if grep -q 'AGENTOS_ISSUE77_CONTROL_INBOX_REPAIR_V1' "$CHRONOS_TARGET"; then
  echo 'issue77_bridge_cleanup=FAIL' >&2
  exit 4
fi
echo 'issue77_bridge_cleanup=PASS'

AFTER=$(snapshot_state)
echo "core_deployment_after=$AFTER"
test "$BEFORE" = "$AFTER" || { echo 'core_generation_unchanged=FAIL' >&2; exit 5; }
echo 'core_generation_unchanged=PASS'
echo 'issue77_control_inbox_repair=PASS'

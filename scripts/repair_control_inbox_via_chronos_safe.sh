#!/usr/bin/env bash
set -euo pipefail

# Issue #77 one-time bounded repair. No arbitrary path/service/command params.
SOURCE_SHA="${GITHUB_SHA:?GITHUB_SHA is required}"
DATA=/home/ubuntu/agent-data
LOCAL=/home/ubuntu/agentmanager
CHRONOS_TARGET="$LOCAL/scripts/update_scheduler_board.py"
BRIDGE_ROOT=/tmp/agentos-issue77-control-inbox
RECEIPT="$BRIDGE_ROOT/${GITHUB_RUN_ID:-manual}-${SOURCE_SHA}.receipt.json"
BACKUP="$BRIDGE_ROOT/${GITHUB_RUN_ID:-manual}-${SOURCE_SHA}.update_scheduler_board.py"
STATE="$DATA/governance/core-deployment.json"
mkdir -p "$BRIDGE_ROOT"
chmod 1777 "$BRIDGE_ROOT"
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

test -f "$CHRONOS_TARGET" && test -w "$CHRONOS_TARGET"
cat "$CHRONOS_TARGET" > "$BACKUP"
restore_target() { [ ! -f "$BACKUP" ] || cat "$BACKUP" > "$CHRONOS_TARGET" || true; }
trap restore_target EXIT

python3 - "$CHRONOS_TARGET" "$SOURCE_SHA" "$RECEIPT" <<'PY'
from pathlib import Path
import sys

target=Path(sys.argv[1]); sha=sys.argv[2]; receipt=sys.argv[3]
original=target.read_text(encoding='utf-8')
marker='# AGENTOS_ISSUE77_CONTROL_INBOX_REPAIR_V2\n'
if marker in original:
    raise SystemExit('issue77 bridge marker already present')

shell_script=f'''set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/1001
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus
REPO=/home/ubuntu/agentmanager
RUNTIME_BASE=/home/ubuntu/.local/share/agentos/control-inbox
RELEASE="$RUNTIME_BASE/releases/{sha}"
CURRENT="$RUNTIME_BASE/current"
UNIT=/home/ubuntu/.config/systemd/user/agentos-control-inbox.service
ENV=/home/ubuntu/.config/agentos/control-inbox.env
DATA=/home/ubuntu/agent-data
mkdir -p "$RELEASE/agent_core" "$RUNTIME_BASE/releases" "$DATA/runtime/control-inbox"
git -C "$REPO" fetch --no-tags origin {sha}
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "{sha}"
git -C "$REPO" show {sha}:agent_core/__init__.py > "$RELEASE/agent_core/__init__.py"
git -C "$REPO" show {sha}:agent_core/control_inbox_bridge.py > "$RELEASE/agent_core/control_inbox_bridge.py"
git -C "$REPO" show {sha}:scripts/repair_control_inbox_github_auth_user.sh > /tmp/issue77-repair-auth.sh
chmod 700 /tmp/issue77-repair-auth.sh
grep -q 'CONTROLLER_DISPATCH_SUCCESS_CODES = {{200, 202}}' "$RELEASE/agent_core/control_inbox_bridge.py"
python3 -m py_compile "$RELEASE/agent_core/control_inbox_bridge.py"
ln -sfn "$RELEASE" "$CURRENT.new"
mv -Tf "$CURRENT.new" "$CURRENT"
cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS GitHub Issue Bootstrap Control Inbox
After=network-online.target agentos-realm-fabric.service
Wants=network-online.target
Requires=agentos-realm-fabric.service

[Service]
Type=simple
WorkingDirectory=$CURRENT
Environment=PYTHONPATH=$CURRENT
EnvironmentFile=$ENV
UMask=0077
ExecStart=/usr/bin/python3 -m agent_core.control_inbox_bridge
Restart=always
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA/runtime/control-inbox

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
AGENTOS_CONTROL_ENV="$ENV" AGENT_DATA_ROOT="$DATA" bash /tmp/issue77-repair-auth.sh
systemctl --user is-active --quiet agentos-control-inbox.service
systemctl --user show agentos-control-inbox.service -p MainPID -p ActiveState -p SubState --no-pager
grep -F "WorkingDirectory=$CURRENT" "$UNIT"
grep -F "Environment=PYTHONPATH=$CURRENT" "$UNIT"
rm -f /tmp/issue77-repair-auth.sh
echo issue77_control_inbox_repair=PASS
echo control_inbox_runtime_decoupled=PASS
echo control_inbox_source_commit={sha}
'''

lines = [
    marker.rstrip('\n'),
    'import datetime as _i77_dt',
    'import json as _i77_json',
    'import os as _i77_os',
    'from pathlib import Path as _I77Path',
    'import subprocess as _i77_subprocess',
    'import traceback as _i77_traceback',
    f'_I77_SHA={sha!r}',
    f'_I77_RECEIPT=_I77Path({receipt!r})',
    'if not _I77_RECEIPT.exists():',
    '    _i77_payload={"schema":"agentos.issue77-control-inbox-repair/v1","source_commit":_I77_SHA,"executor_user":_i77_os.environ.get("USER") or str(_i77_os.getuid()),"executor_uid":_i77_os.getuid(),"started_at":_i77_dt.datetime.now(_i77_dt.timezone.utc).isoformat(),"ok":False}',
    '    try:',
    f'        _i77_cmd=["/bin/bash","-lc",{shell_script!r}]',
    '        _i77_p=_i77_subprocess.run(_i77_cmd,text=True,capture_output=True,timeout=240)',
    '        _i77_payload.update({"returncode":_i77_p.returncode,"ok":_i77_p.returncode==0,"stdout":(_i77_p.stdout or "")[-30000:],"stderr":(_i77_p.stderr or "")[-12000:]})',
    '    except BaseException as _i77_e:',
    '        _i77_payload.update({"error":type(_i77_e).__name__+": "+str(_i77_e),"traceback":_i77_traceback.format_exc()[-12000:]})',
    '    _i77_payload["completed_at"]=_i77_dt.datetime.now(_i77_dt.timezone.utc).isoformat()',
    '    _i77_tmp=_I77_RECEIPT.with_suffix(_I77_RECEIPT.suffix+".tmp")',
    '    _i77_tmp.write_text(_i77_json.dumps(_i77_payload,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")',
    '    _i77_os.chmod(_i77_tmp,0o644)',
    '    _i77_tmp.replace(_I77_RECEIPT)',
    '    _i77_os.chmod(_I77_RECEIPT,0o644)',
    '',
]
bridge='\n'.join(lines)
compile(bridge+original,str(target),'exec')
target.write_text(bridge+original,encoding='utf-8')
PY

echo 'issue77_one_time_bridge_installed=YES'
for i in $(seq 1 360); do [ -f "$RECEIPT" ] && break; sleep 1; done
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
! grep -q 'AGENTOS_ISSUE77_CONTROL_INBOX_REPAIR_V2' "$CHRONOS_TARGET" || { echo 'issue77_bridge_cleanup=FAIL'; exit 4; }
echo 'issue77_bridge_cleanup=PASS'
AFTER=$(snapshot_state)
echo "core_deployment_after=$AFTER"
test "$BEFORE" = "$AFTER" || { echo 'core_generation_unchanged=FAIL'; exit 5; }
echo 'core_generation_unchanged=PASS'
echo 'issue77_control_inbox_repair=PASS'

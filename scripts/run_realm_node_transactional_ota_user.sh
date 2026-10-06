#!/usr/bin/env bash
set -euo pipefail

NODE_ID="${AGENTOS_OTA_NODE_ID:?AGENTOS_OTA_NODE_ID is required}"
CANDIDATE="${AGENTOS_OTA_CANDIDATE_COMMIT:?AGENTOS_OTA_CANDIDATE_COMMIT is required}"
TOOL_COMMIT="${AGENTOS_SOURCE_COMMIT:?AGENTOS_SOURCE_COMMIT is required}"
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"

printf '%s' "$NODE_ID" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
printf '%s' "$CANDIDATE" | grep -Eq '^[0-9a-f]{40}$'
printf '%s' "$TOOL_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

cd "$REPO"
export PYTHONPATH="$REPO"
export NODE_ID CANDIDATE TOOL_COMMIT

python3 - <<'PY'
import os,time
from agent_core.realm_fabric import RealmFabricStore

node=os.environ["NODE_ID"]
candidate=os.environ["CANDIDATE"]
tool=os.environ["TOOL_COMMIT"]
url=f"https://raw.githubusercontent.com/alston-personal/agentmanager/{tool}/scripts/windows/transactional_ota.ps1"
ps=f"$p=Join-Path $env:TEMP 'agentos-transactional-ota.ps1'; Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile $p; & $p -SourceCommit '{candidate}' -ToolCommit '{tool}'"
task_id=f"ota-stage-{node}-{int(time.time())}"
store=RealmFabricStore()
store.queue_task(node,{
    "schema":"agentos.node-task/v0.1",
    "task_id":task_id,
    "action":"shell.exec",
    "executable":"powershell",
    "argv":["-NoProfile","-NonInteractive","-Command",ps],
    "cwd":r"C:\Users\alston.huang\AgentOS",
    "timeout_seconds":120,
    "cognition_ids_used":[],
})
print("node_ota_target="+node)
print("node_ota_candidate_commit="+candidate)
print("node_ota_stage_task="+task_id)
for _ in range(70):
    r=store.get_receipt(task_id)
    if r:
        rc=int(r.get("returncode") if r.get("returncode") is not None else -999)
        out=str(r.get("stdout") or "")
        err=str(r.get("error") or "")
        marker=("agentos_ota_controller_acceptance=PENDING" in out)
        error_class=(err.split(":",1)[0] if err else "none")[:80]
        print("node_ota_stage_receipt_ok="+str(r.get("ok") is True))
        print("node_ota_stage_returncode="+str(rc))
        print("node_ota_stage_pending_marker="+str(marker))
        print("node_ota_stage_error_class="+error_class)
        if r.get("ok") is not True or rc != 0 or not marker:
            raise SystemExit("OTA staging subprocess failed")
        print("node_ota_stage_receipt=PASS")
        break
    time.sleep(2)
else:
    raise SystemExit("OTA staging receipt timeout")
PY

set +e
python3 - <<'PY'
import os
from agent_core.runtime_ota_acceptance import accept_candidate
r=accept_candidate(os.environ["NODE_ID"],os.environ["CANDIDATE"],timeout_seconds=120)
print("node_ota_controller_acceptance="+("PASS" if r.get("ok") else "FAIL"))
print("node_ota_acceptance_stage="+str(r.get("stage") or "unknown"))
print("node_ota_acceptance_reason="+str(r.get("reason") or "none"))
print("node_ota_acceptance_receipt_ok="+str(r.get("receipt_ok") if "receipt_ok" in r else "none"))
if not r.get("ok"):
    raise SystemExit(10)
PY
ACCEPT_RC=$?
set -e

if [ "$ACCEPT_RC" -eq 0 ]; then
  python3 - <<'PY'
import os,time
from agent_core.realm_fabric import RealmFabricStore
node=os.environ["NODE_ID"]; tool=os.environ["TOOL_COMMIT"]
url=f"https://raw.githubusercontent.com/alston-personal/agentmanager/{tool}/scripts/windows/transactional_ota_finalize.ps1"
ps=f"$p=Join-Path $env:TEMP 'agentos-ota-finalize.ps1'; Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile $p; & $p -Action accept"
tid=f"ota-finalize-{node}-{int(time.time())}"
store=RealmFabricStore()
store.queue_task(node,{"schema":"agentos.node-task/v0.1","task_id":tid,"action":"shell.exec","executable":"powershell","argv":["-NoProfile","-NonInteractive","-Command",ps],"cwd":r"C:\Users\alston.huang\AgentOS","timeout_seconds":30,"cognition_ids_used":[]})
print("node_ota_finalize_task="+tid)
for _ in range(60):
    r=store.get_receipt(tid)
    if r:
        out=str(r.get("stdout") or "")
        if r.get("ok") is not True or "agentos_ota_finalize=PASS" not in out:
            raise SystemExit("OTA finalize failed")
        print("node_ota_finalize_receipt=PASS")
        print("node_ota=PASS")
        raise SystemExit(0)
    time.sleep(2)
raise SystemExit("OTA finalize receipt timeout")
PY
else
  python3 - <<'PY'
import os,time
from agent_core.realm_fabric import RealmFabricStore
node=os.environ["NODE_ID"]; tool=os.environ["TOOL_COMMIT"]
url=f"https://raw.githubusercontent.com/alston-personal/agentmanager/{tool}/scripts/windows/transactional_ota_finalize.ps1"
ps=f"$p=Join-Path $env:TEMP 'agentos-ota-finalize.ps1'; Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile $p; & $p -Action rollback"
tid=f"ota-rollback-{node}-{int(time.time())}"
store=RealmFabricStore()
store.queue_task(node,{"schema":"agentos.node-task/v0.1","task_id":tid,"action":"shell.exec","executable":"powershell","argv":["-NoProfile","-NonInteractive","-Command",ps],"cwd":r"C:\Users\alston.huang\AgentOS","timeout_seconds":30,"cognition_ids_used":[]})
print("node_ota_rollback_task="+tid)
for _ in range(90):
    r=store.get_receipt(tid)
    if r:
        out=str(r.get("stdout") or "")
        if r.get("ok") is not True or "agentos_ota_rollback=PASS" not in out:
            raise SystemExit("OTA rollback failed")
        print("node_ota_rollback_receipt=PASS")
        raise SystemExit(10)
    time.sleep(2)
raise SystemExit("OTA rollback receipt timeout")
PY
fi

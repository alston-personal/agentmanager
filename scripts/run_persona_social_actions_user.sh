#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_social_action_runtime=WRONG_USER"; exit 2; }
PERSONA_PATH="${PERSONA_PATH:-personas/sunlake-milkcat}"
SOCIAL_EXECUTOR="${AGENTOS_PERSONA_SOCIAL_EXECUTOR:-$HOME/.local/lib/agentos/persona_social_executor.py}"
REPLY_INTENT_GENERATOR="${AGENTOS_PERSONA_REPLY_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_reply_intent_generator.py}"
POST_INTENT_GENERATOR="${AGENTOS_PERSONA_POST_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_post_intent_generator.py}"
GROWTH_METRICS="${AGENTOS_PERSONA_GROWTH_METRICS:-$HOME/.local/lib/agentos/persona_growth_metrics_collector.py}"
MEDIA_WORKER="${AGENTOS_PERSONA_MEDIA_WORKER:-$HOME/.local/lib/agentos/persona_media_request_worker.py}"
LOCK=/tmp/agentos-persona-pdca-heartbeat.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "persona_social_action_runtime=BUSY"
  exit 0
fi

test -f "$SOCIAL_EXECUTOR"
test -f "$REPLY_INTENT_GENERATOR"
test -f "$POST_INTENT_GENERATOR"
test -f "$GROWTH_METRICS"
command -v gh >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth status >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth setup-git >/dev/null

DATA_REPO="$(mktemp -d /tmp/persona-social-data-XXXXXX)"
cleanup() { rm -rf "$DATA_REPO"; }
trap cleanup EXIT

env -u GH_TOKEN -u GITHUB_TOKEN gh repo clone alston-personal/my-agent-data "$DATA_REPO" -- --branch main --single-branch >/dev/null
git -C "$DATA_REPO" config --unset-all credential.helper || true
git -C "$DATA_REPO" config credential.https://github.com.helper '!/usr/bin/gh auth git-credential'

ROOT="$DATA_REPO/$PERSONA_PATH"
test -f "$ROOT/pdca/state.json"
test -f "$ROOT/events/events.jsonl"

# Fail closed on durable-state corruption. A malformed persona state must be
# reported as DEGRADED before any adapter/cognition work can consume it.
check_persona_state() {
python3 - "$ROOT/pdca/state.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
try:
    value=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("INVALID_STATE_SHAPE")
except (OSError,ValueError) as exc:
    print("persona_social_state_integrity=DEGRADED error="+type(exc).__name__)
    raise SystemExit(3)
print("persona_social_state_integrity=PASS")
PY
}
if ! check_persona_state; then
  echo "persona_social_action_runtime=DEGRADED_STATE" >&2
  exit 3
fi

# Resolve the PDCA-selected read before cognition. This is the existing worker
# lane consuming a durable intent, not another independent patrol cron.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SOCIAL_RECEIPT="$ROOT/pdca/social_receipts/$STAMP.json"
mkdir -p "$(dirname "$SOCIAL_RECEIPT")"
SOCIAL_EXECUTOR_SHA="$(sha256sum "$SOCIAL_EXECUTOR" | cut -d ' ' -f 1)"
python3 "$SOCIAL_EXECUTOR" --persona-dir "$ROOT" --username mio.milkcat --receipt-out "$SOCIAL_RECEIPT"
python3 -m json.tool "$SOCIAL_RECEIPT" >/dev/null

# Optional media failures must not discard a completed observation or stop
# text/reply cognition. Keep raw worker output in the disposable clone only.
MEDIA_WORKER_SHA=""
if [ ! -f "$MEDIA_WORKER" ]; then
  MEDIA_RC=127
else
  MEDIA_WORKER_SHA="$(sha256sum "$MEDIA_WORKER" 2>/dev/null | cut -d ' ' -f 1)" || MEDIA_WORKER_SHA=""
  if python3 "$MEDIA_WORKER" --persona-dir "$ROOT" >"$DATA_REPO/media-worker-output.log" 2>&1; then
    MEDIA_RC=0
  else
    MEDIA_RC=$?
  fi
fi
python3 - "$ROOT" "$MEDIA_RC" "$MEDIA_WORKER_SHA" "$0" "$MEDIA_WORKER" "$SOCIAL_EXECUTOR" "$SOCIAL_EXECUTOR_SHA" <<'PY'
import hashlib,json,os,socket,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(sys.argv[1]); code=int(sys.argv[2]); runner=Path(sys.argv[4])
runtime=(os.getuid()==1001 and socket.gethostname()=="instance-20260129-0852"
         and root.parts[-2:]==("personas","sunlake-milkcat")
         and runner==Path("/home/ubuntu/.local/bin/agentos-persona-social-actions")
         and Path(sys.argv[5])==Path("/home/ubuntu/.local/lib/agentos/persona_media_request_worker.py")
         and Path(sys.argv[6])==Path("/home/ubuntu/.local/lib/agentos/persona_social_executor.py"))
report={"schema":"agentos.execution-receipt/v1","operation":"persona.media.worker.tick",
        "capability":"persona.media.prepare","node":socket.gethostname(),
        "authority":{"kind":"runtime_node" if runtime else "offline_fixture","sandbox_fallback_allowed":False},
        "environment":"production" if runtime else "offline",
        "status":"completed" if code==0 else "failed","exit_code":code,
        "reason":None if code==0 else "MEDIA_WORKER_NOT_INSTALLED" if code==127 else "MEDIA_WORKER_FAILED",
        "expected":{"worker_sha256":sys.argv[3] or None,
                    "runner_sha256":hashlib.sha256(runner.read_bytes()).hexdigest(),
                    "social_executor_sha256":sys.argv[7]},
        "publication_allowed":False,"image_acceptance":"NOT_OBSERVED",
        "media_failure_blocks_social_lane":False}
path=root/"pdca/media_worker_runtime.json"
try:
    previous=json.loads(path.read_text())
except (OSError,ValueError):
    previous={}
if not isinstance(previous,dict) or {k:v for k,v in previous.items() if k!="checked_at"}!=report:
    report["checked_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    temp=path.with_suffix(".tmp"); temp.write_text(json.dumps(report,indent=2)+"\n")
    os.replace(temp,path)
print("persona_social_media_worker="+("PASS" if code==0 else "DEGRADED")+" rc="+str(code))
PY
# A partial media update never authorizes consuming or committing corrupt state.
if ! check_persona_state; then
  echo "persona_social_action_runtime=DEGRADED_STATE" >&2
  exit 3
fi

# Social lane owns bounded social cognition. A reasoning defer/failure is local
# to this lane and never blocks the core PDCA/Observer heartbeat.
if python3 "$REPLY_INTENT_GENERATOR" --persona-dir "$ROOT"; then
  echo "persona_social_reply_intent=PASS"
else
  echo "persona_social_reply_intent=DEGRADED rc=$?" >&2
fi
if python3 "$POST_INTENT_GENERATOR" --persona-dir "$ROOT"; then
  echo "persona_social_post_intent=PASS"
else
  echo "persona_social_post_intent=DEGRADED rc=$?" >&2
fi
METRICS_RECEIPT="$ROOT/pdca/growth_metrics/$STAMP.json"
mkdir -p "$(dirname "$METRICS_RECEIPT")"
if python3 "$GROWTH_METRICS" --persona-dir "$ROOT" --username mio.milkcat --receipt-out "$METRICS_RECEIPT"; then
  python3 -m json.tool "$METRICS_RECEIPT" >/dev/null
  # Avoid durable noise from repeated unchanged metric polls. Keep the first
  # receipt for a status transition, but suppress repeated UNAVAILABLE/NO_CHANGE.
  python3 - "$ROOT/pdca/growth_metrics" "$METRICS_RECEIPT" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); current=Path(sys.argv[2])
cur=json.loads(current.read_text(encoding="utf-8"))
status=str(cur.get("status") or "")
changed=int(cur.get("changed") or 0)
previous=[]
for p in sorted(root.glob("*.json")):
    if p == current:
        continue
    try:
        previous.append(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
prev_status=str(previous[-1].get("status") or "") if previous else ""
if changed == 0 and status in {"UNAVAILABLE","NO_CHANGE"} and prev_status == status:
    current.unlink(missing_ok=True)
    print("persona_growth_metrics_persist=SUPPRESSED_REPEAT")
else:
    print("persona_growth_metrics_persist=KEPT")
PY
else
  # A metrics outage must not discard the observation or incident in this clone.
  python3 - "$METRICS_RECEIPT" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status":"ERROR","changed":0})+"\n",encoding="utf-8")
PY
fi

STATUS="$(python3 -c "import json; print(json.load(open('$SOCIAL_RECEIPT')).get('status',''))")"
if [ "$STATUS" = "NO_ACTION" ]; then
  rm -f "$SOCIAL_RECEIPT"
fi

METRICS_STATUS="NO_CHANGE"
METRICS_CHANGED="0"
if [ -f "$METRICS_RECEIPT" ]; then
  METRICS_STATUS="$(python3 -c "import json; print(json.load(open('$METRICS_RECEIPT')).get('status','unknown'))")"
  METRICS_CHANGED="$(python3 -c "import json; print(json.load(open('$METRICS_RECEIPT')).get('changed',0))")"
fi

cd "$DATA_REPO"
git config user.name 'agentos-persona-social[bot]'
git config user.email 'agentos-persona-social[bot]@users.noreply.github.com'
git add "$PERSONA_PATH/pdca" "$PERSONA_PATH/events/events.jsonl"
if git diff --cached --quiet; then
  echo "persona_social_action_runtime=NO_ACTION"
  exit 0
fi

git commit -m "persona(mio): persist autonomous social action" >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' push >/dev/null

if [ "$STATUS" = "NO_ACTION" ]; then
  echo "persona_social_action_runtime=METRICS_ONLY"
  echo "persona_growth_metrics_status=$METRICS_STATUS"
  echo "persona_growth_metrics_changed=$METRICS_CHANGED"
else
  python3 - "$SOCIAL_RECEIPT" "$METRICS_STATUS" "$METRICS_CHANGED" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
assert r.get("status") in ("EXECUTED","BLOCKED","AWAITING_READBACK","WRITE_OUTCOME_UNKNOWN","RECONCILIATION_PENDING","RECONCILED"),r
classification=("PENDING_READBACK" if r.get("status") in ("AWAITING_READBACK","RECONCILIATION_PENDING") else
                "PASS" if r.get("status")=="RECONCILED" and r.get("delivery_confirmed") is True else
                "WRITE_OUTCOME_UNKNOWN" if r.get("status")=="WRITE_OUTCOME_UNKNOWN" else
                "PASS" if r.get("ok") is True else "BLOCKED")
print("persona_social_action_runtime="+classification)
print("persona_social_action_capability="+str(r.get("capability") or "unknown"))
print("persona_social_action_write="+("unknown" if r.get("write_performed") is None else str(bool(r.get("write_performed"))).lower()))
print("persona_growth_metrics_status="+sys.argv[2])
print("persona_growth_metrics_changed="+sys.argv[3])
PY
fi

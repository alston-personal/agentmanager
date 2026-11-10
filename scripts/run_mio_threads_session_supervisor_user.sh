#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_threads_session_supervisor=WRONG_USER" >&2
  exit 2
fi

ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}/runtime/mio-threads-session-supervisor"
mkdir -p "$ROOT/incidents"
chmod 700 "$ROOT" "$ROOT/incidents"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set +e
OUT="$("$SCRIPT_DIR/probe_threads_web_dm_login_user.sh" 2>&1)"
RC=$?
set -e

STATE="$(printf '%s\n' "$OUT" | sed -n 's/^threads_web_dm_login_session_state=//p' | tail -n1)"
[ -n "$STATE" ] || STATE="PROBE_ERROR"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STATUS="$ROOT/status.json"
PREV=""
if [ -f "$STATUS" ]; then
  PREV="$(python3 - "$STATUS" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
    print(str(d.get('session_state') or ''))
except Exception:
    pass
PY
)"
fi

python3 - "$STATUS" "$NOW" "$STATE" "$RC" <<'PY'
import json,os,sys,tempfile
path,now,state,rc=sys.argv[1:5]
payload={
  "schema":"agentos.mio-threads-session-supervisor/v1",
  "checked_at":now,
  "session_state":state,
  "probe_rc":int(rc),
}
fd,tmp=tempfile.mkstemp(prefix=".status-",dir=os.path.dirname(path))
os.close(fd)
with open(tmp,"w",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,indent=2,sort_keys=True); f.write("\n")
os.chmod(tmp,0o600); os.replace(tmp,path)
PY

if [ "$STATE" != "AUTHENTICATED" ] && [ "$STATE" != "$PREV" ]; then
  SAFE_STATE="$(printf '%s' "$STATE" | tr -cd 'A-Za-z0-9_.:-')"
  INCIDENT="$ROOT/incidents/$(date -u +%Y%m%dT%H%M%SZ)-$SAFE_STATE.json"
  python3 - "$INCIDENT" "$NOW" "$STATE" <<'PY'
import json,os,sys
path,now,state=sys.argv[1:4]
payload={
  "schema":"agentos.session-incident/v1",
  "project":"mio",
  "platform":"threads",
  "account":"mio.milkcat",
  "failure_class":"threads_session_"+state.lower(),
  "session_state":state,
  "observed_at":now,
  "human_action_required": state in {"LOGIN_REQUIRED","BLOCKED"},
}
with open(path,"x",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,indent=2,sort_keys=True); f.write("\n")
os.chmod(path,0o600)
PY
fi

echo "mio_threads_session_supervisor_state=$STATE"
echo "mio_threads_session_supervisor_transition=$([ "$STATE" = "$PREV" ] && echo false || echo true)"
if [ "$RC" -ne 0 ] && [ "$STATE" = "PROBE_ERROR" ]; then
  exit "$RC"
fi

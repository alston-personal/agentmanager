#!/bin/bash
set -euo pipefail

REF="${1:-core/integration}"
ONE_URL="${AGENTOS_ONE_URL:-http://127.0.0.1:8780}"
NODE_ID="${AGENTOS_NODE_ID:-oracle-exec}"
ROOT="$HOME/.local/share/AgentOS"
VENV="$ROOT/venv"
STATE="$HOME/.agentos-oracle-exec"
WORKSPACE="$HOME/AgentOS"
LAUNCHER="$ROOT/agentos-client"

command -v python3 >/dev/null || { echo "python3 is required"; exit 2; }
command -v git >/dev/null || { echo "git is required"; exit 2; }
command -v systemctl >/dev/null || { echo "systemctl is required"; exit 2; }

mkdir -p "$ROOT" "$STATE" "$WORKSPACE"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade "git+https://github.com/alston-personal/agentmanager.git@$REF"

cat > "$LAUNCHER" <<EOF
#!/bin/bash
export AGENTOS_CLIENT_HOME="$STATE"
exec "$VENV/bin/agentos-client" "\$@"
EOF
chmod 700 "$LAUNCHER"

if [ ! -f "$STATE/policy.json" ]; then
  cat > "$STATE/policy.json" <<EOF
{
  "schema": "agentos.client-policy/v0.1",
  "allowed_executables": ["git", "python3", "systemctl", "ss"],
  "readable_roots": ["$WORKSPACE"],
  "writable_roots": ["$WORKSPACE"],
  "employee_wake_root": null,
  "max_timeout_seconds": 120
}
EOF
  chmod 600 "$STATE/policy.json"
fi

if [ ! -f "$STATE/client.json" ]; then
  if curl -fsS --max-time 3 "$ONE_URL/v1/health" >/dev/null 2>&1; then
    INVITE_JSON="$(AGENT_DATA_ROOT=/home/ubuntu/agent-data PYTHONPATH=/home/ubuntu/agentmanager python3 -m agent_core.realm_cli invite --minutes 10 --label oracle-exec-bootstrap)"
    INVITE_ID="$(printf '%s' "$INVITE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["invite_id"])')"
    INVITE_CODE="$(printf '%s' "$INVITE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["code"])')"
    "$LAUNCHER" enroll --one "$ONE_URL" --invite-id "$INVITE_ID" --code "$INVITE_CODE" --node-id "$NODE_ID" >/dev/null
    unset INVITE_JSON INVITE_ID INVITE_CODE
    echo "agentos_oracle_exec_enrollment=LOCAL_INVITE_PASS"
  else
    echo "agentos_oracle_exec_install=ENROLLMENT_REQUIRED"
    echo "agentos_node_id=$NODE_ID"
    exec "$LAUNCHER" join --one "$ONE_URL" --node-id "$NODE_ID" --timeout-seconds 900
  fi
fi

"$VENV/bin/python" - <<'PY'
from agentos_node.onboarding import install_linux_node_supervisor
import json
r=install_linux_node_supervisor()
print(json.dumps(r, ensure_ascii=False))
if not r.get("supervisor_ready"):
    raise SystemExit(2)
PY
"$LAUNCHER" health
"$LAUNCHER" once
echo "agentos_oracle_exec_install=PASS"
echo "agentos_node_id=$NODE_ID"

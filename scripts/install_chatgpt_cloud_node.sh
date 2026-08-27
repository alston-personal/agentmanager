#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${AGENTOS_CONFIG_ENV_FILE:-$HOME/agentmanager/.env}"
DIST_ENV_FILE="${AGENTOS_DISTRIBUTED_ENV_FILE:-$HOME/.config/agentos/distributed.env}"
SECRETS_FILE="${AGENTOS_SECRETS_FILE:-$HOME/.agentos.secrets}"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
PYTHON_BIN="${AGENTOS_DISTRIBUTED_PYTHON:-}"

[ -f "$ENV_FILE" ] || { echo "Missing AgentOS env: $ENV_FILE" >&2; exit 2; }
[ -f "$DIST_ENV_FILE" ] || { echo "Missing distributed env: $DIST_ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
source "$DIST_ENV_FILE"
[ -f "$SECRETS_FILE" ] && source "$SECRETS_FILE"
set +a

if [ -z "$PYTHON_BIN" ] && [ -x "$LOGIC_ROOT/.venv/bin/python3" ]; then PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"; fi
if [ -z "$PYTHON_BIN" ]; then PYTHON_BIN="$(command -v python3)"; fi
[ -x "$PYTHON_BIN" ] || { echo "No usable Python interpreter found" >&2; exit 2; }
"$PYTHON_BIN" -c 'from mcp.server.mcpserver import MCPServer; assert MCPServer' >/dev/null 2>&1 || {
  echo "Python MCP SDK v2 server API is missing; install/upgrade requirements-mcp.txt into $PYTHON_BIN environment" >&2
  exit 2
}

[ -n "${AGENTOS_CHATGPT_PRINCIPAL_ID:-}" ] || { echo "AGENTOS_CHATGPT_PRINCIPAL_ID is required" >&2; exit 2; }
[ -n "${AGENTOS_CONTROL_PLANE_DB:-}" ] || { echo "AGENTOS_CONTROL_PLANE_DB is required" >&2; exit 2; }

touch "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"

# Reconcile the durable credential with the declared ChatGPT project scope.
# Scope changes rotate the token instead of weakening gateway authorization.
export AGENTOS_CHATGPT_CLIENT_TOKEN="${AGENTOS_CHATGPT_CLIENT_TOKEN:-}"
RECONCILE_JSON="$(PYTHONPATH="$LOGIC_ROOT" "$PYTHON_BIN" - <<'PY'
import json
import os
from agent_core.client_auth import ClientTokenStore
from agent_core.distributed_control_plane import DistributedControlPlane

principal_id = os.environ["AGENTOS_CHATGPT_PRINCIPAL_ID"]
raw_projects = os.environ.get("AGENTOS_CHATGPT_PROJECTS", "*")
expected_projects = tuple(sorted({p.strip() for p in raw_projects.split(",") if p.strip()})) or ("*",)
expected_subject = f"chatgpt:{principal_id}"
expected_permissions = ("project.read", "task.read")
expected_capabilities = ("*",)
existing_token = os.environ.get("AGENTOS_CHATGPT_CLIENT_TOKEN", "").strip()
store = ClientTokenStore(DistributedControlPlane(os.environ["AGENTOS_CONTROL_PLANE_DB"]))
principal = store.principal(existing_token) if existing_token else None
matches = bool(
    principal
    and principal.subject == expected_subject
    and tuple(sorted(principal.permissions)) == tuple(sorted(expected_permissions))
    and tuple(sorted(principal.projects)) == expected_projects
    and tuple(sorted(principal.capabilities)) == expected_capabilities
)
if matches:
    token = existing_token
    rotated = False
else:
    if existing_token and principal is not None:
        store.revoke(existing_token)
    issued = store.issue(
        expected_subject,
        label="ChatGPT Cloud Node",
        permissions=expected_permissions,
        projects=expected_projects,
        capabilities=expected_capabilities,
        ttl_days=90,
    )
    token = issued["token"]
    rotated = True
print(json.dumps({
    "token": token,
    "rotated": rotated,
    "subject": expected_subject,
    "projects": list(expected_projects),
    "permissions": list(expected_permissions),
}, sort_keys=True))
PY
)"
AGENTOS_CHATGPT_CLIENT_TOKEN="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<< "$RECONCILE_JSON")"
export AGENTOS_CHATGPT_CLIENT_TOKEN
TOKEN_ROTATED="$($PYTHON_BIN -c 'import json,sys; print("1" if json.load(sys.stdin)["rotated"] else "0")' <<< "$RECONCILE_JSON")"

# Replace every stale token assignment atomically while preserving unrelated secrets.
"$PYTHON_BIN" - "$SECRETS_FILE" "$AGENTOS_CHATGPT_CLIENT_TOKEN" <<'PY'
from pathlib import Path
import os, sys, tempfile
path = Path(sys.argv[1])
token = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
lines = [line for line in lines if not line.startswith("AGENTOS_CHATGPT_CLIENT_TOKEN=")]
lines.append(f"AGENTOS_CHATGPT_CLIENT_TOKEN={token}")
fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
PY
chmod 600 "$SECRETS_FILE"
if [ "$TOKEN_ROTATED" = "1" ]; then
  echo "one_principal_scope_reconciled=rotated"
else
  echo "one_principal_scope_reconciled=reused"
fi

# Prove the credential resolves in the exact ONE database and matches declared scope
# before touching the running gateway.
PYTHONPATH="$LOGIC_ROOT" "$PYTHON_BIN" - <<'PY'
import os
from agent_core.client_auth import ClientTokenStore
from agent_core.distributed_control_plane import DistributedControlPlane

token = os.environ["AGENTOS_CHATGPT_CLIENT_TOKEN"]
db = os.environ["AGENTOS_CONTROL_PLANE_DB"]
expected_subject = f"chatgpt:{os.environ['AGENTOS_CHATGPT_PRINCIPAL_ID']}"
expected_projects = tuple(sorted({p.strip() for p in os.environ.get("AGENTOS_CHATGPT_PROJECTS", "*").split(",") if p.strip()})) or ("*",)
principal = ClientTokenStore(DistributedControlPlane(db)).principal(token)
assert principal is not None, "ChatGPT client token is not present/active in the configured ONE database"
assert principal.subject == expected_subject, (principal.subject, expected_subject)
assert principal.allows_permission("project.read"), principal.permissions
assert principal.allows_permission("task.read"), principal.permissions
assert tuple(sorted(principal.projects)) == expected_projects, (principal.projects, expected_projects)
print("one_principal_db=ok")
print(f"one_principal_subject={principal.subject}")
print(f"one_principal_permissions={','.join(principal.permissions)}")
print(f"one_principal_projects={','.join(principal.projects)}")
PY

# The release checkout may have advanced while the long-running Control Plane
# still has older Python modules loaded. Restart it so scoped-auth semantics and
# the code used by the MCP service come from the same deployed revision.
systemctl --user restart agentos-control-plane.service
CONTROL_READY=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then
    CONTROL_READY=1
    break
  fi
  sleep 1
done
if [ "$CONTROL_READY" != "1" ]; then
  echo "Control Plane did not become healthy after ChatGPT Cloud refresh" >&2
  systemctl --user --no-pager --full status agentos-control-plane.service >&2 || true
  journalctl --user -u agentos-control-plane.service -n 120 --no-pager >&2 || true
  exit 7
fi
echo "one_control_plane_refresh=ok"

mkdir -p "$USER_SYSTEMD_DIR" "$DATA_ROOT/logs"

cat > "$USER_SYSTEMD_DIR/agentos-chatgpt-mcp.service" <<EOF
[Unit]
Description=AgentOS ChatGPT Cloud Node MCP
After=network-online.target agentos-control-plane.service
Requires=agentos-control-plane.service

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
Environment=PYTHONPATH=$LOGIC_ROOT
Environment=AGENTOS_CONTROL_PLANE_URL=http://127.0.0.1:8765
Environment=AGENTOS_CHATGPT_RUNTIME_ID=chatgpt-web
Environment=AGENTOS_MCP_HOST=127.0.0.1
Environment=AGENTOS_MCP_PORT=${AGENTOS_MCP_PORT:-8000}
Environment=AGENTOS_MCP_PATH=${AGENTOS_MCP_PATH:-/mcp}
EnvironmentFile=-$ENV_FILE
EnvironmentFile=-$DIST_ENV_FILE
EnvironmentFile=-$SECRETS_FILE
ExecStart=$PYTHON_BIN scripts/agentos_mcp_server.py
Restart=always
RestartSec=5
StandardOutput=append:$DATA_ROOT/logs/chatgpt_mcp.log
StandardError=append:$DATA_ROOT/logs/chatgpt_mcp.log

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable agentos-chatgpt-mcp.service >/dev/null
systemctl --user restart agentos-chatgpt-mcp.service
systemctl --user is-active --quiet agentos-chatgpt-mcp.service

echo "Installed AgentOS ChatGPT Cloud Node"
echo "ONE: http://127.0.0.1:8765"
echo "MCP: http://127.0.0.1:${AGENTOS_MCP_PORT:-8000}${AGENTOS_MCP_PATH:-/mcp}"
echo "Identity scope: account"
echo "Principal: ${AGENTOS_CHATGPT_PRINCIPAL_ID}"

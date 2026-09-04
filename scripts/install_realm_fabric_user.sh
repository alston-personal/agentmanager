#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$LOGIC_ROOT/.env"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
[ -f "$HOME/.agentos.secrets" ] && source "$HOME/.agentos.secrets"
set +a

if [ "${AGENT_MODE:-CLIENT}" != "CORE" ]; then
  echo "Realm Fabric service may only be installed on a CORE node" >&2
  exit 2
fi

DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
FABRIC_FILE="$DATA_ROOT/realm/fabric.json"
REQUESTED_REALM_ID="${AGENTOS_REALM_ID:-}"
PORT="${AGENTOS_REALM_FABRIC_PORT:-8780}"
PYTHON_BIN="$LOGIC_ROOT/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"; fi
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN="$(command -v python3)"; fi

# Existing durable Realm identity is authoritative. A missing AGENTOS_REALM_ID
# must never silently replace an enrolled Realm with the historical
# "realm-primary" default. An explicit conflicting value is a fail-closed
# configuration error rather than permission to rewrite fabric identity.
if [ -f "$FABRIC_FILE" ]; then
  EXISTING_REALM_ID="$(python3 - "$FABRIC_FILE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
realm_id = str(payload.get("realm_id") or "").strip()
if not realm_id:
    raise SystemExit(2)
print(realm_id)
PY
)"
  if [ -n "$REQUESTED_REALM_ID" ] && [ "$REQUESTED_REALM_ID" != "$EXISTING_REALM_ID" ]; then
    echo "Configured AGENTOS_REALM_ID does not match existing Realm fabric" >&2
    exit 4
  fi
  REALM_ID="$EXISTING_REALM_ID"
else
  REALM_ID="${REQUESTED_REALM_ID:-realm-primary}"
fi

mkdir -p "$USER_SYSTEMD_DIR" "$DATA_ROOT/logs"
AGENT_DATA_ROOT="$DATA_ROOT" "$PYTHON_BIN" -m agent_core.realm_cli init --realm-id "$REALM_ID"

cat > "$USER_SYSTEMD_DIR/agentos-realm-fabric.service" <<EOF
[Unit]
Description=AgentOS ONE Realm Fabric
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
Environment=AGENT_DATA_ROOT=$DATA_ROOT
ExecStart=$PYTHON_BIN -m agent_core.realm_cli serve --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=5
StandardOutput=append:$DATA_ROOT/logs/realm-fabric.log
StandardError=append:$DATA_ROOT/logs/realm-fabric.log

[Install]
WantedBy=default.target
EOF

# Writing a new unit while the service is already active does not replace the
# running Python process. enable --now alone therefore leaves stale code and a
# stale Core manifest in memory. Always reload, enable, then explicitly restart
# so the process re-reads the exact deployed checkout before acceptance.
systemctl --user daemon-reload
systemctl --user enable agentos-realm-fabric.service
systemctl --user restart agentos-realm-fabric.service
systemctl --user is-active --quiet agentos-realm-fabric.service
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/v1/health"
echo
echo "realm_id=$REALM_ID"
echo "realm_fabric_port=$PORT"

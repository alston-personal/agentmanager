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
REALM_ID="${AGENTOS_REALM_ID:-realm-primary}"
PORT="${AGENTOS_REALM_FABRIC_PORT:-8780}"
PYTHON_BIN="$LOGIC_ROOT/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"; fi
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN="$(command -v python3)"; fi

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

systemctl --user daemon-reload
systemctl --user enable --now agentos-realm-fabric.service
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/v1/health"
echo
echo "realm_id=$REALM_ID"
echo "realm_fabric_port=$PORT"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_ROOT="${AGENTOS_CONFIG_ROOT:-$HOME/agentmanager}"
ENV_FILE="${AGENTOS_CONFIG_ENV_FILE:-$CONFIG_ROOT/.env}"
DIST_ENV_FILE="${AGENTOS_DISTRIBUTED_ENV_FILE:-$HOME/.config/agentos/distributed.env}"
SECRETS_FILE="${AGENTOS_SECRETS_FILE:-$HOME/.agentos.secrets}"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

[ -f "$ENV_FILE" ] || { echo "Missing base AgentOS env: $ENV_FILE" >&2; exit 2; }
[ -f "$DIST_ENV_FILE" ] || { echo "Missing Distributed AgentOS env: $DIST_ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
source "$DIST_ENV_FILE"
[ -f "$SECRETS_FILE" ] && source "$SECRETS_FILE"
set +a

[ "${AGENTOS_DISTRIBUTED_SERVICES_ENABLED:-0}" = "1" ] || { echo "AGENTOS_DISTRIBUTED_SERVICES_ENABLED must be 1" >&2; exit 2; }
[ -n "${AGENTOS_CONTROL_PLANE_TOKEN:-}" ] || { echo "AGENTOS_CONTROL_PLANE_TOKEN is required" >&2; exit 2; }

DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
PYTHON_BIN="${AGENTOS_DISTRIBUTED_PYTHON:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "$LOGIC_ROOT/.venv/bin/python3" ]; then PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"; fi
if [ -z "$PYTHON_BIN" ]; then PYTHON_BIN="$(command -v python3)"; fi
[ -x "$PYTHON_BIN" ] || { echo "No usable Python interpreter found" >&2; exit 2; }
mkdir -p "$USER_SYSTEMD_DIR" "$DATA_ROOT/logs"

cat > "$USER_SYSTEMD_DIR/agentos-control-plane.service" <<EOF
[Unit]
Description=Distributed AgentOS Control Plane and Runtime Dispatcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
Environment=AGENT_PROJECT_ROOT=$LOGIC_ROOT
Environment=PYTHONPATH=$LOGIC_ROOT
EnvironmentFile=-$ENV_FILE
EnvironmentFile=-$DIST_ENV_FILE
EnvironmentFile=-$SECRETS_FILE
ExecStart=$PYTHON_BIN scripts/distributed_gateway.py
Restart=always
RestartSec=5
StandardOutput=append:$DATA_ROOT/logs/distributed_control_plane.log
StandardError=append:$DATA_ROOT/logs/distributed_control_plane.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/agentos-node.service" <<EOF
[Unit]
Description=AgentOS Oracle Native Execution Node
After=network-online.target agentos-control-plane.service
Requires=agentos-control-plane.service

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
Environment=AGENT_PROJECT_ROOT=$LOGIC_ROOT
Environment=PYTHONPATH=$LOGIC_ROOT
Environment=AGENTOS_CONTROL_PLANE_URL=http://127.0.0.1:8765
Environment=AGENTOS_RUNTIME_ID=oracle-core-node
EnvironmentFile=-$ENV_FILE
EnvironmentFile=-$DIST_ENV_FILE
EnvironmentFile=-$SECRETS_FILE
ExecStart=$PYTHON_BIN scripts/agentos_node_daemon.py
Restart=always
RestartSec=2
StandardOutput=append:$DATA_ROOT/logs/agentos_node.log
StandardError=append:$DATA_ROOT/logs/agentos_node.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/agentos-provider-bridge.service" <<EOF
[Unit]
Description=Distributed AgentOS Provider Bridge
After=network-online.target agentos-control-plane.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
Environment=AGENT_PROJECT_ROOT=$LOGIC_ROOT
Environment=PYTHONPATH=$LOGIC_ROOT
EnvironmentFile=-$ENV_FILE
EnvironmentFile=-$DIST_ENV_FILE
EnvironmentFile=-$SECRETS_FILE
ExecStart=$PYTHON_BIN scripts/provider_bridge.py
Restart=always
RestartSec=5
StandardOutput=append:$DATA_ROOT/logs/provider_bridge.log
StandardError=append:$DATA_ROOT/logs/provider_bridge.log

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable agentos-control-plane.service agentos-node.service >/dev/null
systemctl --user restart agentos-control-plane.service
systemctl --user restart agentos-node.service

if [ "${AGENTOS_PROVIDER_BRIDGE_ENABLED:-0}" = "1" ]; then
  [ -n "${AGENTOS_PROVIDER_BRIDGE_TOKEN:-}" ] || { echo "AGENTOS_PROVIDER_BRIDGE_ENABLED=1 requires AGENTOS_PROVIDER_BRIDGE_TOKEN" >&2; exit 2; }
  if [ -z "${AGENTOS_PROVIDER_ROUTES_FILE:-}" ] && [ -z "${AGENTOS_PROVIDER_ROUTES_JSON:-}" ]; then
    echo "Provider Bridge requires AGENTOS_PROVIDER_ROUTES_FILE or AGENTOS_PROVIDER_ROUTES_JSON" >&2; exit 2
  fi
  systemctl --user enable agentos-provider-bridge.service >/dev/null
  systemctl --user restart agentos-provider-bridge.service
else
  systemctl --user stop agentos-provider-bridge.service 2>/dev/null || true
  systemctl --user disable agentos-provider-bridge.service 2>/dev/null || true
fi

echo "Installed isolated Distributed AgentOS services from $LOGIC_ROOT"
echo "Python: $PYTHON_BIN"
echo "Native node: oracle-core-node"
echo "Data logs: $DATA_ROOT/logs"

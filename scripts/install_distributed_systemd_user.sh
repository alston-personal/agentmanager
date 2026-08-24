#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_ROOT="${AGENTOS_CONFIG_ROOT:-$HOME/agentmanager}"
ENV_FILE="${AGENTOS_CONFIG_ENV_FILE:-$CONFIG_ROOT/.env}"
DIST_ENV_FILE="${AGENTOS_DISTRIBUTED_ENV_FILE:-$HOME/.config/agentos/distributed.env}"
SECRETS_FILE="${AGENTOS_SECRETS_FILE:-$HOME/.agentos.secrets}"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing base AgentOS env: $ENV_FILE" >&2
  exit 2
fi
if [ ! -f "$DIST_ENV_FILE" ]; then
  echo "Missing Distributed AgentOS env: $DIST_ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
# shellcheck disable=SC1090
source "$DIST_ENV_FILE"
# shellcheck disable=SC1090
[ -f "$SECRETS_FILE" ] && source "$SECRETS_FILE"
set +a

if [ "${AGENTOS_DISTRIBUTED_SERVICES_ENABLED:-0}" != "1" ]; then
  echo "AGENTOS_DISTRIBUTED_SERVICES_ENABLED must be 1 in $DIST_ENV_FILE" >&2
  exit 2
fi
if [ -z "${AGENTOS_CONTROL_PLANE_TOKEN:-}" ]; then
  echo "AGENTOS_CONTROL_PLANE_TOKEN is required in $SECRETS_FILE" >&2
  exit 2
fi

DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
PYTHON_BIN="${AGENTOS_DISTRIBUTED_PYTHON:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "$LOGIC_ROOT/.venv/bin/python3" ]; then
  PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"
fi
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi
if [ ! -x "$PYTHON_BIN" ]; then
  echo "No usable Python interpreter found for Distributed AgentOS" >&2
  exit 2
fi

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
systemctl --user enable agentos-control-plane.service >/dev/null
systemctl --user restart agentos-control-plane.service

if [ "${AGENTOS_PROVIDER_BRIDGE_ENABLED:-0}" = "1" ]; then
  if [ -z "${AGENTOS_PROVIDER_BRIDGE_TOKEN:-}" ]; then
    echo "AGENTOS_PROVIDER_BRIDGE_ENABLED=1 requires AGENTOS_PROVIDER_BRIDGE_TOKEN" >&2
    exit 2
  fi
  if [ -z "${AGENTOS_PROVIDER_ROUTES_FILE:-}" ] && [ -z "${AGENTOS_PROVIDER_ROUTES_JSON:-}" ]; then
    echo "Provider Bridge requires AGENTOS_PROVIDER_ROUTES_FILE or AGENTOS_PROVIDER_ROUTES_JSON" >&2
    exit 2
  fi
  systemctl --user enable agentos-provider-bridge.service >/dev/null
  systemctl --user restart agentos-provider-bridge.service
else
  systemctl --user stop agentos-provider-bridge.service 2>/dev/null || true
  systemctl --user disable agentos-provider-bridge.service 2>/dev/null || true
fi

echo "Installed isolated Distributed AgentOS services from $LOGIC_ROOT"
echo "Python: $PYTHON_BIN"
echo "Base config: $ENV_FILE"
echo "Distributed config: $DIST_ENV_FILE"
echo "Data logs: $DATA_ROOT/logs"

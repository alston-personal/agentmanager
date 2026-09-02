#!/usr/bin/env bash
set -euo pipefail

# Install AgentOS user-level systemd units using the current checkout paths.
# This keeps cloned machines portable instead of relying on hard-coded service files.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$LOGIC_ROOT/.env"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env. Copy .env.example to .env and fill it before installing services."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
[ -f "$HOME/.agentos.secrets" ] && source "$HOME/.agentos.secrets"
set +a

DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
PYTHON_BIN="$LOGIC_ROOT/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"
fi
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

SUPERVISOR_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/agentos"
SUPERVISOR_ENV_FILE="$SUPERVISOR_CONFIG_DIR/core-supervisor.env"
SUPERVISOR_DELIVERY_ENV_FILE="$SUPERVISOR_CONFIG_DIR/core-supervisor-delivery.env"
SUPERVISOR_UNIT_SRC="$LOGIC_ROOT/.agent/scripts/agentos-core-supervisor.service"
SUPERVISOR_UNIT_DST="$USER_SYSTEMD_DIR/agentos-core-supervisor.service"
SUPERVISOR_DELIVERY_DROPIN_SRC="$LOGIC_ROOT/.agent/scripts/agentos-core-supervisor-delivery.conf.example"
SUPERVISOR_DROPIN_DIR="$USER_SYSTEMD_DIR/agentos-core-supervisor.service.d"
SUPERVISOR_DELIVERY_DROPIN_DST="$SUPERVISOR_DROPIN_DIR/20-one-direct-filesystem.conf"

EMPLOYEE_WORKER_ENV_FILE="$SUPERVISOR_CONFIG_DIR/employee-worker-host.env"
EMPLOYEE_WORKER_UNIT_SRC="$LOGIC_ROOT/.agent/scripts/agentos-employee-worker-host.service"
EMPLOYEE_WORKER_UNIT_DST="$USER_SYSTEMD_DIR/agentos-employee-worker-host.service"
EMPLOYEE_WORKER_WAKE_ROOT="${AGENTOS_EMPLOYEE_WAKE_ROOT:-}"
EMPLOYEE_WORKER_HOST_STATE_ROOT="${AGENTOS_EMPLOYEE_WORKER_HOST_STATE_ROOT:-$DATA_ROOT/employee-worker-host}"
EMPLOYEE_WORKER_STATE_ROOT="${AGENTOS_EMPLOYEE_WORKER_STATE_ROOT:-$DATA_ROOT/employee-worker-state}"
EMPLOYEE_WORKER_NODE_ID="${AGENTOS_EMPLOYEE_WORKER_NODE_ID:-}"

mkdir -p "$USER_SYSTEMD_DIR" "$DATA_ROOT/logs"

render_supervisor_asset() {
  local src="$1"
  local dst="$2"
  "$PYTHON_BIN" - "$src" "$dst" "$LOGIC_ROOT" "$SUPERVISOR_ENV_FILE" "$SUPERVISOR_DELIVERY_ENV_FILE" "$PYTHON_BIN" "$DATA_ROOT" <<'PY'
from pathlib import Path
import sys

src, dst, logic_root, env_file, delivery_env_file, python_bin, data_root = sys.argv[1:]
text = Path(src).read_text(encoding="utf-8")
replacements = {
    "/home/ubuntu/agentmanager": logic_root,
    "/home/ubuntu/.config/agentos/core-supervisor.env": env_file,
    "/home/ubuntu/.config/agentos/core-supervisor-delivery.env": delivery_env_file,
    "/usr/bin/python3": python_bin,
    "/home/ubuntu/agent-data/employee-runtime": str(Path(data_root) / "employee-runtime"),
    "/home/ubuntu/agent-data/realm": str(Path(data_root) / "realm"),
}
for old, new in replacements.items():
    text = text.replace(old, new)
Path(dst).parent.mkdir(parents=True, exist_ok=True)
Path(dst).write_text(text, encoding="utf-8")
PY
}

render_employee_worker_asset() {
  local src="$1"
  local dst="$2"
  "$PYTHON_BIN" - "$src" "$dst" "$LOGIC_ROOT" "$EMPLOYEE_WORKER_ENV_FILE" "$PYTHON_BIN" "$DATA_ROOT" "$EMPLOYEE_WORKER_WAKE_ROOT" "$EMPLOYEE_WORKER_HOST_STATE_ROOT" "$EMPLOYEE_WORKER_STATE_ROOT" <<'PY'
from pathlib import Path
import sys

(
    src,
    dst,
    logic_root,
    env_file,
    python_bin,
    data_root,
    wake_root,
    host_state_root,
    worker_state_root,
) = sys.argv[1:]
text = Path(src).read_text(encoding="utf-8")
replacements = {
    "/home/ubuntu/agentmanager": logic_root,
    "/home/ubuntu/.config/agentos/employee-worker-host.env": env_file,
    "/usr/bin/python3": python_bin,
    "/home/ubuntu/agent-data/employee-runtime": str(Path(data_root) / "employee-runtime"),
    "/home/ubuntu/agent-data/employee-wake-inbox": wake_root,
    "/home/ubuntu/agent-data/employee-worker-host": host_state_root,
    "/home/ubuntu/agent-data/employee-worker-state": worker_state_root,
}
for old, new in replacements.items():
    text = text.replace(old, new)
Path(dst).parent.mkdir(parents=True, exist_ok=True)
Path(dst).write_text(text, encoding="utf-8")
PY
}

install_core_supervisor() {
  test -f "$SUPERVISOR_UNIT_SRC" || { echo "Missing Supervisor service asset: $SUPERVISOR_UNIT_SRC" >&2; exit 2; }
  test -f "$SUPERVISOR_DELIVERY_DROPIN_SRC" || { echo "Missing Supervisor delivery asset: $SUPERVISOR_DELIVERY_DROPIN_SRC" >&2; exit 2; }

  mkdir -p "$SUPERVISOR_CONFIG_DIR" "$SUPERVISOR_DROPIN_DIR" "$DATA_ROOT/employee-runtime"
  render_supervisor_asset "$SUPERVISOR_UNIT_SRC" "$SUPERVISOR_UNIT_DST"

  # First install is deliberately S3-only. Existing host-local configuration is
  # never replaced wholesale by the repository example.
  if [ ! -f "$SUPERVISOR_ENV_FILE" ]; then
    cat > "$SUPERVISOR_ENV_FILE" <<EOF
AGENTOS_EMPLOYEE_RUNTIME_ROOT=$DATA_ROOT/employee-runtime
AGENTOS_SUPERVISOR_SERVICE_ID=agentos-core-supervisor
AGENTOS_SUPERVISOR_BASE_POLL_SECONDS=5
AGENTOS_SUPERVISOR_MAX_POLL_SECONDS=60
AGENTOS_SUPERVISOR_LEADER_LEASE_SECONDS=30
AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled
EOF
    chmod 600 "$SUPERVISOR_ENV_FILE"
  fi

  if [ "${AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT:-0}" = "1" ]; then
    test -f "$DATA_ROOT/realm/fabric.json" || {
      echo "Refusing Supervisor one_direct: missing existing $DATA_ROOT/realm/fabric.json" >&2
      exit 2
    }
    test -f "$DATA_ROOT/realm/nodes.json" || {
      echo "Refusing Supervisor one_direct: missing existing $DATA_ROOT/realm/nodes.json" >&2
      exit 2
    }
    render_supervisor_asset "$SUPERVISOR_DELIVERY_DROPIN_SRC" "$SUPERVISOR_DELIVERY_DROPIN_DST"
    cat > "$SUPERVISOR_DELIVERY_ENV_FILE" <<EOF
AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct
AGENTOS_SUPERVISOR_ONE_DATA_ROOT=$DATA_ROOT
EOF
    chmod 600 "$SUPERVISOR_DELIVERY_ENV_FILE"
  else
    if grep -Eq '^AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct([[:space:]]*)$' "$SUPERVISOR_ENV_FILE"; then
      echo "Refusing Supervisor install: host env requests one_direct without AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1" >&2
      exit 2
    fi
    rm -f "$SUPERVISOR_DELIVERY_ENV_FILE" "$SUPERVISOR_DELIVERY_DROPIN_DST"
  fi
}

install_employee_worker_host() {
  test -f "$EMPLOYEE_WORKER_UNIT_SRC" || {
    echo "Missing Employee Worker Host service asset: $EMPLOYEE_WORKER_UNIT_SRC" >&2
    exit 2
  }
  if [ -z "$EMPLOYEE_WORKER_WAKE_ROOT" ]; then
    echo "Refusing Employee Worker Host install: AGENTOS_EMPLOYEE_WAKE_ROOT is required" >&2
    exit 2
  fi
  case "$EMPLOYEE_WORKER_WAKE_ROOT" in
    /*) ;;
    *)
      echo "Refusing Employee Worker Host install: AGENTOS_EMPLOYEE_WAKE_ROOT must be absolute" >&2
      exit 2
      ;;
  esac
  test -d "$EMPLOYEE_WORKER_WAKE_ROOT" || {
    echo "Refusing Employee Worker Host install: configured wake root does not already exist" >&2
    exit 2
  }
  if [ -z "$EMPLOYEE_WORKER_NODE_ID" ]; then
    echo "Refusing Employee Worker Host install: AGENTOS_EMPLOYEE_WORKER_NODE_ID is required" >&2
    exit 2
  fi
  if printf '%s' "$EMPLOYEE_WORKER_NODE_ID" | grep -Eq '[/\\]'; then
    echo "Refusing Employee Worker Host install: invalid AGENTOS_EMPLOYEE_WORKER_NODE_ID" >&2
    exit 2
  fi

  mkdir -p "$SUPERVISOR_CONFIG_DIR" "$DATA_ROOT/employee-runtime" "$EMPLOYEE_WORKER_HOST_STATE_ROOT" "$EMPLOYEE_WORKER_STATE_ROOT"
  render_employee_worker_asset "$EMPLOYEE_WORKER_UNIT_SRC" "$EMPLOYEE_WORKER_UNIT_DST"

  if [ ! -f "$EMPLOYEE_WORKER_ENV_FILE" ]; then
    cat > "$EMPLOYEE_WORKER_ENV_FILE" <<EOF
AGENTOS_EMPLOYEE_RUNTIME_ROOT=$DATA_ROOT/employee-runtime
AGENTOS_EMPLOYEE_WAKE_ROOT=$EMPLOYEE_WORKER_WAKE_ROOT
AGENTOS_EMPLOYEE_WORKER_HOST_STATE_ROOT=$EMPLOYEE_WORKER_HOST_STATE_ROOT
AGENTOS_EMPLOYEE_WORKER_STATE_ROOT=$EMPLOYEE_WORKER_STATE_ROOT
AGENTOS_EMPLOYEE_WORKER_NODE_ID=$EMPLOYEE_WORKER_NODE_ID
AGENTOS_EMPLOYEE_WORKER_POLL_SECONDS=2
AGENTOS_EMPLOYEE_WORKER_CHILD_TIMEOUT_SECONDS=180
AGENTOS_EMPLOYEE_WORKER_LEASE_SECONDS=60
EOF
    chmod 600 "$EMPLOYEE_WORKER_ENV_FILE"
  fi
}

cat > "$USER_SYSTEMD_DIR/os-chronos.service" <<EOF
[Unit]
Description=AgentOS Central Chronos Scheduler
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/chronos.py
Restart=always
RestartSec=30
StandardOutput=append:$DATA_ROOT/logs/chronos.log
StandardError=append:$DATA_ROOT/logs/chronos.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/agent-maintenance.service" <<EOF
[Unit]
Description=AgentOS Periodic Maintenance and Watchdog
After=network.target

[Service]
Type=oneshot
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/maintenance.py
StandardOutput=append:$DATA_ROOT/logs/maintenance.log
StandardError=append:$DATA_ROOT/logs/maintenance.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/agent-maintenance.timer" <<EOF
[Unit]
Description=Run AgentOS maintenance every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Unit=agent-maintenance.service

[Install]
WantedBy=timers.target
EOF

cat > "$USER_SYSTEMD_DIR/tg-commander.service" <<EOF
[Unit]
Description=AgentOS Telegram Command Bridge
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/tg_bridge.py
Restart=always
RestartSec=10
StandardOutput=append:$DATA_ROOT/logs/tg_bridge.log
StandardError=append:$DATA_ROOT/logs/tg_bridge.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/teams-commander.service" <<EOF
[Unit]
Description=AgentOS Teams Command Bridge
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/teams_bridge.py
Restart=always
RestartSec=10
StandardOutput=append:$DATA_ROOT/logs/teams_bridge.log
StandardError=append:$DATA_ROOT/logs/teams_bridge.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/cat-ink-syncer.service" <<EOF
[Unit]
Description=AgentOS Cat-Ink Session Syncer
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/core_services/session_syncer.py
Restart=always
RestartSec=30
StandardOutput=append:$DATA_ROOT/logs/cat_ink_syncer.log
StandardError=append:$DATA_ROOT/logs/cat_ink_syncer.log

[Install]
WantedBy=default.target
EOF

cat > "$USER_SYSTEMD_DIR/os-lobster.service" <<EOF
[Unit]
Description=AgentOS Lobster Autonomous Task Loop
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/lobster.py --loop
Restart=always
RestartSec=30
StandardOutput=append:$DATA_ROOT/logs/lobster.log
StandardError=append:$DATA_ROOT/logs/lobster.log

[Install]
WantedBy=default.target
EOF

if [ "${AGENT_MODE:-CLIENT}" = "CORE" ]; then
  install_core_supervisor
  if [ "${AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE:-0}" = "1" ]; then
    install_employee_worker_host
  fi
fi

systemctl --user daemon-reload

# Stop and disable legacy pulse service if it exists
systemctl --user stop os-pulse.service 2>/dev/null || true
systemctl --user disable os-pulse.service 2>/dev/null || true

# Stop legacy PM2 zeus-autonomous-manager if running
if command -v pm2 &>/dev/null; then
  pm2 delete zeus-autonomous-manager 2>/dev/null || true
  pm2 save 2>/dev/null || true
fi

systemctl --user enable os-chronos.service agent-maintenance.timer teams-commander.service >/dev/null
systemctl --user restart teams-commander.service

if [ "${AGENT_MODE:-CLIENT}" = "CORE" ]; then
  systemctl --user enable tg-commander.service cat-ink-syncer.service os-lobster.service >/dev/null
  systemctl --user restart tg-commander.service
  systemctl --user restart cat-ink-syncer.service
  systemctl --user restart os-lobster.service
  systemctl --user enable agentos-core-supervisor.service >/dev/null
  systemctl --user restart agentos-core-supervisor.service
  if [ "${AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE:-0}" = "1" ]; then
    systemctl --user enable agentos-employee-worker-host.service >/dev/null
    systemctl --user restart agentos-employee-worker-host.service
  else
    systemctl --user disable --now agentos-employee-worker-host.service 2>/dev/null || true
  fi
else
  systemctl --user disable --now agentos-core-supervisor.service 2>/dev/null || true
  systemctl --user disable --now agentos-employee-worker-host.service 2>/dev/null || true
  echo "AGENT_MODE is not CORE; tg-commander.service, cat-ink-syncer.service, os-lobster.service, agentos-core-supervisor.service, and agentos-employee-worker-host.service are not started."
fi

systemctl --user restart os-chronos.service
systemctl --user start agent-maintenance.timer

echo "Installed AgentOS user services from $LOGIC_ROOT"
echo "Data logs: $DATA_ROOT/logs"

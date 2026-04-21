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
set +a

DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

mkdir -p "$USER_SYSTEMD_DIR" "$DATA_ROOT/logs"

cat > "$USER_SYSTEMD_DIR/os-pulse.service" <<EOF
[Unit]
Description=AgentOS Heartbeat Pulse Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN scripts/pulse.py --agent Architect --task "Heartbeat Monitor" --status active --watch
Restart=always
RestartSec=30
StandardOutput=append:$DATA_ROOT/logs/pulse.log
StandardError=append:$DATA_ROOT/logs/pulse.log

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

systemctl --user daemon-reload
systemctl --user enable os-pulse.service agent-maintenance.timer >/dev/null

if [ "${AGENT_MODE:-CLIENT}" = "CORE" ]; then
  systemctl --user enable tg-commander.service cat-ink-syncer.service >/dev/null
  systemctl --user restart tg-commander.service
  systemctl --user restart cat-ink-syncer.service
else
  echo "AGENT_MODE is not CORE; tg-commander.service and cat-ink-syncer.service installed but not started."
fi

systemctl --user restart os-pulse.service
systemctl --user start agent-maintenance.timer

echo "Installed AgentOS user services from $LOGIC_ROOT"
echo "Data logs: $DATA_ROOT/logs"

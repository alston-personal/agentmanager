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

mkdir -p "$USER_SYSTEMD_DIR" "$DATA_ROOT/logs" "$DATA_ROOT/config"

CREDITS_PORT="$(
  AGENT_DATA_ROOT="$DATA_ROOT" PYTHONPATH="$LOGIC_ROOT" "$PYTHON_BIN" - <<'PY'
import contextlib
import io
from scripts.core_services.port_manager import allocate_port
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    port = allocate_port(
        "milkcat-credits",
        "Milkcat Credits loopback HTTP",
        start_port=3000,
        end_port=8999,
    )
print(port)
PY
)"
case "$CREDITS_PORT" in
  ''|*[!0-9]*) echo "Invalid governed Milkcat Credits port: $CREDITS_PORT" >&2; exit 1 ;;
esac
CREDITS_ENV="$DATA_ROOT/config/milkcat_credits.env"
cat > "$CREDITS_ENV" <<EOF
MILKCAT_CREDITS_PORT=$CREDITS_PORT
MILKCAT_CREDITS_URL=http://127.0.0.1:$CREDITS_PORT
EOF
chmod 600 "$CREDITS_ENV"

cat > "$USER_SYSTEMD_DIR/milkcat-credits.service" <<EOF
[Unit]
Description=Milkcat Credits shadow metering service
After=network.target

[Service]
Type=simple
WorkingDirectory=$LOGIC_ROOT
EnvironmentFile=$ENV_FILE
EnvironmentFile=-%h/.agentos.secrets
EnvironmentFile=$CREDITS_ENV
Environment=MILKCAT_CREDITS_MODE=shadow
ExecStart=$PYTHON_BIN -m agent_core.credit_http --host 127.0.0.1 --port $CREDITS_PORT
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
StandardOutput=append:$DATA_ROOT/logs/milkcat_credits.log
StandardError=append:$DATA_ROOT/logs/milkcat_credits.log

[Install]
WantedBy=default.target
EOF

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
  systemctl --user enable tg-commander.service cat-ink-syncer.service os-lobster.service milkcat-credits.service >/dev/null
  systemctl --user restart tg-commander.service
  systemctl --user restart cat-ink-syncer.service
  systemctl --user restart os-lobster.service
  systemctl --user restart milkcat-credits.service
  for attempt in {1..10}; do
    if curl -fsS --max-time 2 "http://127.0.0.1:$CREDITS_PORT/healthz" | grep -q '"service": "milkcat-credits"'; then
      break
    fi
    if [ "$attempt" -eq 10 ]; then
      echo "milkcat-credits.service failed loopback health verification" >&2
      systemctl --user --no-pager --full status milkcat-credits.service || true
      exit 1
    fi
    sleep 1
  done
else
  echo "AGENT_MODE is not CORE; tg-commander.service, cat-ink-syncer.service, and os-lobster.service installed but not started."
fi

systemctl --user restart os-chronos.service
systemctl --user start agent-maintenance.timer

echo "Installed AgentOS user services from $LOGIC_ROOT"
echo "Data logs: $DATA_ROOT/logs"

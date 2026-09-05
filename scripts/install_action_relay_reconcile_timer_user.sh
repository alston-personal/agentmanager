#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
ENV_FILE="$REPO/.env"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$UNIT_DIR/agentos-action-relay-reconcile.service"
TIMER="$UNIT_DIR/agentos-action-relay-reconcile.timer"
LOG="$DATA_ROOT/logs/action-relay-reconcile.log"

case "$REPO" in
  /*) ;;
  *) echo "ERROR: AGENTOS_REPO must be absolute" >&2; exit 2 ;;
esac

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
test -f "$ENV_FILE" || { echo "ERROR: env missing: $ENV_FILE" >&2; exit 2; }
test -f "$REPO/scripts/reconcile_action_relay_runtime.py" || { echo "ERROR: reconciler missing" >&2; exit 2; }
id -Gn ubuntu | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: ubuntu must belong to agentos group" >&2; exit 3; }

PYTHON_BIN="$REPO/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$REPO/.venv/bin/python3"
fi
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

mkdir -p "$UNIT_DIR" "$DATA_ROOT/logs"

cat > "$SERVICE" <<EOF
[Unit]
Description=AgentOS Action Relay Immutable Generation Reconciler
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$REPO
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/sg agentos -c 'exec $PYTHON_BIN $REPO/scripts/reconcile_action_relay_runtime.py'
StandardOutput=append:$LOG
StandardError=append:$LOG

[Install]
WantedBy=default.target
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Reconcile AgentOS Action Relay immutable generation

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
Unit=agentos-action-relay-reconcile.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-action-relay-reconcile.timer >/dev/null

# Installing the timer must not restart the Action Relay from inside a live
# relay request. The timer owns future reconciliation; a separate explicit
# start is intentionally omitted here.
systemctl --user is-enabled --quiet agentos-action-relay-reconcile.timer

echo "action_relay_reconcile_timer_install=PASS"
echo "service=$SERVICE"
echo "timer=$TIMER"
echo "log=$LOG"

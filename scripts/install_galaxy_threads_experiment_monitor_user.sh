#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "galaxy_experiment_monitor_install=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$UNIT_DIR/agentos-galaxy-experiment-monitor.service"
TIMER="$UNIT_DIR/agentos-galaxy-experiment-monitor.timer"
LOG_DIR="$HOME/agent-data/logs"
LOG="$LOG_DIR/galaxy-experiment-monitor.log"

test -f "$REPO/scripts/monitor_galaxy_threads_experiment_user.py"
mkdir -p "$UNIT_DIR" "$LOG_DIR"

cat > "$SERVICE" <<EOF
[Unit]
Description=AgentOS Threads AI Subscription Experiment Monitor
After=network-online.target agentos-social-runtime.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 $REPO/scripts/monitor_galaxy_threads_experiment_user.py
StandardOutput=append:$LOG
StandardError=append:$LOG

[Install]
WantedBy=default.target
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Monitor Threads AI Subscription Experiment

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true
Unit=agentos-galaxy-experiment-monitor.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-galaxy-experiment-monitor.timer >/dev/null
systemctl --user start agentos-galaxy-experiment-monitor.service
systemctl --user is-enabled --quiet agentos-galaxy-experiment-monitor.timer
systemctl --user is-active --quiet agentos-galaxy-experiment-monitor.timer

echo "galaxy_experiment_monitor_install=PASS"
echo "galaxy_experiment_monitor_interval=30m"
echo "galaxy_experiment_monitor_log=$LOG"

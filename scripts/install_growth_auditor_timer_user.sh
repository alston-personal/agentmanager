#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DATA_ROOT="${AGENT_DATA_ROOT:-$HOME/agent-data}"
PYTHON_BIN="$LOGIC_ROOT/venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$LOGIC_ROOT/.venv/bin/python3"
fi
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

mkdir -p "$UNIT_DIR" "$DATA_ROOT/logs" "$DATA_ROOT/growth-proof"

cat > "$UNIT_DIR/agentos-growth-auditor.service" <<EOF
[Unit]
Description=AgentOS Growth Proof Auditor
After=network.target

[Service]
Type=oneshot
WorkingDirectory=$LOGIC_ROOT
Environment=AGENT_DATA_ROOT=$DATA_ROOT
ExecStart=$PYTHON_BIN scripts/growth_auditor_tick.py --receipt-out $DATA_ROOT/growth-proof/last-auditor-receipt.json
NoNewPrivileges=true
PrivateTmp=true
StandardOutput=append:$DATA_ROOT/logs/growth_auditor.log
StandardError=append:$DATA_ROOT/logs/growth_auditor.log
EOF

cat > "$UNIT_DIR/agentos-growth-auditor.timer" <<EOF
[Unit]
Description=Run AgentOS Growth Proof Auditor every 5 minutes

[Timer]
OnCalendar=*-*-* *:0/5:00
Persistent=true
AccuracySec=30s
Unit=agentos-growth-auditor.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-growth-auditor.timer >/dev/null
systemctl --user is-enabled --quiet agentos-growth-auditor.timer
systemctl --user is-active --quiet agentos-growth-auditor.timer

echo "growth_auditor_timer_install=PASS"
echo "growth_auditor_interval=5m"
echo "growth_auditor_ledger=$DATA_ROOT/growth-proof/ledger.json"

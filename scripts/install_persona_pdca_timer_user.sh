#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_pdca_timer_install=WRONG_USER"; exit 2; }
SOURCE_TICK="${1:-}"
SOURCE_RUNNER="${2:-}"
SOURCE_SOCIAL_EXECUTOR="${3:-}"
test -f "$SOURCE_TICK"
test -f "$SOURCE_RUNNER"
test -f "$SOURCE_SOCIAL_EXECUTOR"

LIB="$HOME/.local/lib/agentos"
BIN="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$LIB" "$BIN" "$UNIT_DIR"
install -m 0755 "$SOURCE_TICK" "$LIB/persona_pdca_tick.py"
install -m 0755 "$SOURCE_SOCIAL_EXECUTOR" "$LIB/persona_social_executor.py"
install -m 0755 "$SOURCE_RUNNER" "$BIN/agentos-persona-pdca-heartbeat"

SERVICE="$UNIT_DIR/agentos-persona-pdca-heartbeat.service"
TIMER="$UNIT_DIR/agentos-persona-pdca-heartbeat.timer"

cat > "$SERVICE" <<EOF
[Unit]
Description=AgentOS Persona PDCA Heartbeat
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=PERSONA_PATH=personas/sunlake-milkcat
Environment=AGENTOS_PERSONA_PDCA_TICK=$LIB/persona_pdca_tick.py
Environment=AGENTOS_PERSONA_SOCIAL_EXECUTOR=$LIB/persona_social_executor.py
ExecStart=$BIN/agentos-persona-pdca-heartbeat
NoNewPrivileges=true
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=AgentOS Persona PDCA Hourly Heartbeat

[Timer]
OnActiveSec=55min
OnUnitActiveSec=60min
AccuracySec=2min
Unit=agentos-persona-pdca-heartbeat.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-persona-pdca-heartbeat.timer >/dev/null
systemctl --user is-enabled --quiet agentos-persona-pdca-heartbeat.timer
systemctl --user is-active --quiet agentos-persona-pdca-heartbeat.timer
echo "persona_pdca_timer_install=PASS"
echo "persona_pdca_timer_interval=60m"
echo "persona_pdca_timer_first_due=55m"

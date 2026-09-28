#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_pdca_timer_install=WRONG_USER"; exit 2; }
SOURCE_TICK="${1:-}"
SOURCE_RUNNER="${2:-}"
SOURCE_SOCIAL_EXECUTOR="${3:-}"
SOURCE_INTERNAL_EXECUTOR="${4:-}"
SOURCE_REPLY_INTENT_GENERATOR="${5:-}"
SOURCE_POST_INTENT_GENERATOR="${6:-}"
SOURCE_SOCIAL_RUNNER="${7:-}"
test -f "$SOURCE_TICK"
test -f "$SOURCE_RUNNER"
test -f "$SOURCE_SOCIAL_EXECUTOR"
test -f "$SOURCE_INTERNAL_EXECUTOR"
test -f "$SOURCE_REPLY_INTENT_GENERATOR"
test -f "$SOURCE_PUBLIC_ACTIVITY_PUBLISHER"
test -f "$SOURCE_POST_INTENT_GENERATOR"
test -f "$SOURCE_SOCIAL_RUNNER"

LIB="$HOME/.local/lib/agentos"
BIN="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$LIB" "$BIN" "$UNIT_DIR"
install -m 0755 "$SOURCE_TICK" "$LIB/persona_pdca_tick.py"
install -m 0755 "$SOURCE_SOCIAL_EXECUTOR" "$LIB/persona_social_executor.py"
install -m 0755 "$SOURCE_INTERNAL_EXECUTOR" "$LIB/persona_internal_activity_executor.py"
install -m 0755 "$SOURCE_REPLY_INTENT_GENERATOR" "$LIB/persona_reply_intent_generator.py"
install -m 0755 "$SOURCE_PUBLIC_ACTIVITY_PUBLISHER" "$LIB/publish_mio_public_activity.py"
install -m 0755 "$SOURCE_POST_INTENT_GENERATOR" "$LIB/persona_post_intent_generator.py"
install -m 0755 "$SOURCE_RUNNER" "$BIN/agentos-persona-pdca-heartbeat"
install -m 0755 "$SOURCE_SOCIAL_RUNNER" "$BIN/agentos-persona-social-actions"

SERVICE="$UNIT_DIR/agentos-persona-pdca-heartbeat.service"
TIMER="$UNIT_DIR/agentos-persona-pdca-heartbeat.timer"
SOCIAL_SERVICE="$UNIT_DIR/agentos-persona-social-actions.service"
SOCIAL_TIMER="$UNIT_DIR/agentos-persona-social-actions.timer"

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
Environment=AGENTOS_PERSONA_INTERNAL_EXECUTOR=$LIB/persona_internal_activity_executor.py
Environment=AGENTOS_PERSONA_REPLY_INTENT_GENERATOR=$LIB/persona_reply_intent_generator.py
Environment=AGENTOS_PERSONA_POST_INTENT_GENERATOR=$LIB/persona_post_intent_generator.py
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

cat > "$SOCIAL_SERVICE" <<EOF
[Unit]
Description=AgentOS Persona Social Action Executor
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=PERSONA_PATH=personas/sunlake-milkcat
Environment=AGENTOS_PERSONA_SOCIAL_EXECUTOR=$LIB/persona_social_executor.py
ExecStart=$BIN/agentos-persona-social-actions
NoNewPrivileges=true
EOF

cat > "$SOCIAL_TIMER" <<EOF
[Unit]
Description=AgentOS Persona Social Action Short-Cycle Timer

[Timer]
OnActiveSec=3min
OnUnitActiveSec=5min
AccuracySec=45s
Unit=agentos-persona-social-actions.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-persona-pdca-heartbeat.timer agentos-persona-social-actions.timer >/dev/null
systemctl --user is-enabled --quiet agentos-persona-pdca-heartbeat.timer
systemctl --user is-active --quiet agentos-persona-pdca-heartbeat.timer
systemctl --user is-enabled --quiet agentos-persona-social-actions.timer
systemctl --user is-active --quiet agentos-persona-social-actions.timer
echo "persona_pdca_timer_install=PASS"
echo "persona_pdca_timer_interval=60m"
echo "persona_pdca_timer_first_due=55m"
echo "persona_social_action_timer_install=PASS"
echo "persona_social_action_timer_interval=5m"

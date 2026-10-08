#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_pdca_timer_install=WRONG_USER"; exit 2; }
SOURCE_TICK="${1:-}"
SOURCE_RUNNER="${2:-}"
SOURCE_SOCIAL_EXECUTOR="${3:-}"
SOURCE_INTERNAL_EXECUTOR="${4:-}"
SOURCE_REPLY_INTENT_GENERATOR="${5:-}"
SOURCE_PUBLIC_ACTIVITY_PUBLISHER="${6:-}"
SOURCE_POST_INTENT_GENERATOR="${7:-}"
SOURCE_SOCIAL_RUNNER="${8:-}"
SOURCE_GROWTH_METRICS="${9:-}"
SOURCE_MEDIA_WORKER="${10:-}"
SOURCE_IMAGE_EXECUTOR="${11:-}"
SOURCE_EXPERIENCE_LEDGER="${12:-}"
test -f "$SOURCE_TICK"
test -f "$SOURCE_RUNNER"
test -f "$SOURCE_SOCIAL_EXECUTOR"
test -f "$SOURCE_INTERNAL_EXECUTOR"
test -f "$SOURCE_REPLY_INTENT_GENERATOR"
test -f "$SOURCE_PUBLIC_ACTIVITY_PUBLISHER"
test -f "$SOURCE_POST_INTENT_GENERATOR"
test -f "$SOURCE_SOCIAL_RUNNER"
test -f "$SOURCE_GROWTH_METRICS"
test -f "$SOURCE_MEDIA_WORKER"
test -f "$SOURCE_IMAGE_EXECUTOR"
test -f "$SOURCE_EXPERIENCE_LEDGER"

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
install -m 0755 "$SOURCE_GROWTH_METRICS" "$LIB/persona_growth_metrics_collector.py"
install -m 0755 "$SOURCE_MEDIA_WORKER" "$LIB/persona_media_request_worker.py"
install -m 0755 "$SOURCE_IMAGE_EXECUTOR" "$LIB/persona_image_generate_flux.py"
install -m 0755 "$SOURCE_EXPERIENCE_LEDGER" "$LIB/capability_experience_ledger.py"
CANONICAL_HEARTBEAT="$BIN/agentos-persona-pdca-heartbeat-v2"
install -m 0755 "$SOURCE_RUNNER" "$CANONICAL_HEARTBEAT"
cmp -s "$SOURCE_RUNNER" "$CANONICAL_HEARTBEAT" || {
  echo "persona_pdca_runtime_install=CONTENT_MISMATCH"
  exit 4
}
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
Environment=AGENTOS_MIO_PUBLIC_ACTIVITY_PUBLISHER=$LIB/publish_mio_public_activity.py
Environment=AGENTOS_MIO_PUBLIC_ACTIVITY_OUTPUT=/home/ubuntu/zeus-writer/website/dist/personas/mio/activity.json
Environment=AGENTOS_PERSONA_POST_INTENT_GENERATOR=$LIB/persona_post_intent_generator.py
ExecStart=$CANONICAL_HEARTBEAT
NoNewPrivileges=true
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=AgentOS Persona PDCA Hourly Heartbeat

[Timer]
OnCalendar=*-*-* *:25:00
Persistent=true
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
Environment=AGENTOS_PERSONA_GROWTH_METRICS=$LIB/persona_growth_metrics_collector.py
Environment=AGENTOS_MIO_IMAGE_EXECUTOR=$LIB/persona_image_generate_flux.py
Environment=AGENTOS_MIO_IMAGE_EXECUTOR_PYTHON=/home/ubuntu/.local/share/mio-tryon-venv/bin/python
Environment=AGENTOS_MIO_MEDIA_OUTPUT_DIR=/home/ubuntu/agent-data/media/mio/generated
ExecStart=$BIN/agentos-persona-social-actions
NoNewPrivileges=true
EOF

cat > "$SOCIAL_TIMER" <<EOF
[Unit]
Description=AgentOS Persona Social Action Short-Cycle Timer

[Timer]
OnCalendar=*-*-* *:0/5:00
Persistent=true
AccuracySec=45s
Unit=agentos-persona-social-actions.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable agentos-persona-pdca-heartbeat.timer agentos-persona-social-actions.timer >/dev/null

# Maintenance must not reset an already-running natural cadence. Start only
# timers that are currently inactive; leave active timer scheduling untouched.
if ! systemctl --user is-active --quiet agentos-persona-pdca-heartbeat.timer; then
  systemctl --user start agentos-persona-pdca-heartbeat.timer
fi
if ! systemctl --user is-active --quiet agentos-persona-social-actions.timer; then
  systemctl --user start agentos-persona-social-actions.timer
fi

systemctl --user is-enabled --quiet agentos-persona-pdca-heartbeat.timer
systemctl --user is-active --quiet agentos-persona-pdca-heartbeat.timer
systemctl --user is-enabled --quiet agentos-persona-social-actions.timer
systemctl --user is-active --quiet agentos-persona-social-actions.timer

# One-time liveness recovery: deployment is not a heartbeat source. Canonical
# persona state is the source of truth; systemd unit timestamps can be reset by
# reload/reinstall and must not be used to infer persona liveness.
STALE_AFTER_SEC=5400
RECOVER_STALE=1
STATE_CONTENT="$(env -u GH_TOKEN -u GITHUB_TOKEN gh api   "repos/alston-personal/my-agent-data/contents/personas/sunlake-milkcat/pdca/state.json"   --jq .content 2>/dev/null | tr -d '\n' | base64 -d 2>/dev/null || true)"
if [ -n "$STATE_CONTENT" ]; then
  LAST_TICK="$(printf '%s' "$STATE_CONTENT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("last_tick_at",""))' 2>/dev/null || true)"
  if [ -n "$LAST_TICK" ]; then
    LAST_EPOCH="$(date -d "$LAST_TICK" +%s 2>/dev/null || echo 0)"
    NOW_EPOCH="$(date +%s)"
    if [ "$LAST_EPOCH" -gt 0 ] && [ $((NOW_EPOCH-LAST_EPOCH)) -le "$STALE_AFTER_SEC" ]; then
      RECOVER_STALE=0
    fi
  fi
fi
if [ "$RECOVER_STALE" -eq 1 ]; then
  systemctl --user start agentos-persona-pdca-heartbeat.service
  echo "persona_pdca_stale_recovery=TRIGGERED"
else
  echo "persona_pdca_stale_recovery=SKIPPED_FRESH"
fi

# Installation acceptance is structural only.
# Do not start the heartbeat here: deployments must not advance autonomous cycles
# or reset the natural systemd timer cadence.
systemctl --user is-failed --quiet agentos-persona-pdca-heartbeat.service && {
  systemctl --user --no-pager --full status agentos-persona-pdca-heartbeat.service || true
  exit 5
}
echo "persona_pdca_install_live_cycle=SKIPPED"
echo "persona_pdca_install_reason=installer_must_not_advance_autonomous_cycle"

systemctl --user show -p ExecStart --value agentos-persona-pdca-heartbeat.service | grep -F "$CANONICAL_HEARTBEAT" >/dev/null
echo "persona_pdca_runtime_owner=$CANONICAL_HEARTBEAT"
echo "persona_pdca_timer_install=PASS"
echo "persona_pdca_timer_interval=60m"
echo "persona_pdca_timer_schedule=calendar_:25_persistent"
echo "persona_social_action_timer_install=PASS"
echo "persona_social_action_timer_interval=5m"
echo "persona_social_action_timer_schedule=calendar_5m_persistent"

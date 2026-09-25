#!/usr/bin/env bash
set -euo pipefail

[ "$(id -un)" = ubuntu ] || { echo 'mio_social_resume=WRONG_USER'; exit 2; }
SHA="${AGENTOS_SOURCE_COMMIT:-}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'mio_social_resume=SOURCE_REQUIRED'; exit 3; }

REPO="$HOME/agentmanager"
SERVICE="agentos-galaxy-experiment-monitor.service"
TIMER="agentos-galaxy-experiment-monitor.timer"
UNIT="$HOME/.config/systemd/user/$SERVICE"
DROP_DIR="$HOME/.config/systemd/user/$SERVICE.d"
PAUSE_DROP="$DROP_DIR/50-owner-review-required.conf"
ENABLE_DROP="$DROP_DIR/60-owner-social-enabled.conf"
LOG="$HOME/agent-data/logs/galaxy-experiment-monitor.log"

test -f "$UNIT" || { echo 'mio_social_resume=MONITOR_NOT_INSTALLED'; exit 4; }

# Materialize the exact owner-authorized generation. Keep identity, event sync,
# IR evolution and the social loop on one immutable source generation.
for rel in   scripts/sync_sunlake_milkcat_persona_user.py   scripts/evolve_mio_persona_ir_user.py   scripts/mio_persona_social_loop_user.py; do
  tmp="$(mktemp)"
  git -C "$REPO" show "$SHA:$rel" > "$tmp"
  python3 -m py_compile "$tmp"
  install -m 0644 "$tmp" "$REPO/$rel"
  rm -f "$tmp"
done

grep -Fq "canonical current Persona IR" "$REPO/scripts/mio_persona_social_loop_user.py"
grep -Fq "MIO_SOCIAL_AUTO_REPLY_ALLOWED" "$REPO/scripts/mio_persona_social_loop_user.py"
grep -Fq "interests_with_evidence" "$REPO/scripts/mio_persona_social_loop_user.py"

# Never interrupt an in-flight write. Stop future timer ticks and wait for the
# current oneshot to finish before changing the policy drop-in.
systemctl --user stop "$TIMER" || true
for _ in $(seq 1 90); do
  if ! systemctl --user is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl --user is-active --quiet "$SERVICE"; then
  echo 'mio_social_resume=WAITING_FOR_EXISTING_RUN'
  exit 5
fi

mkdir -p "$DROP_DIR"
rm -f "$PAUSE_DROP"
cat > "$ENABLE_DROP.tmp" <<'EOF'
[Service]
Environment=MIO_SOCIAL_AUTO_REPLY_ALLOWED=owner_explicitly_enabled
ExecStartPost=
ExecStartPost=/bin/sh -c '/usr/bin/python3 /home/ubuntu/agentmanager/scripts/sync_sunlake_milkcat_persona_user.py && /usr/bin/python3 /home/ubuntu/agentmanager/scripts/evolve_mio_persona_ir_user.py && /usr/bin/python3 /home/ubuntu/agentmanager/scripts/mio_persona_social_loop_user.py || { echo mio_persona_cycle=DEFERRED; exit 0; }'
EOF
chmod 0644 "$ENABLE_DROP.tmp"
mv "$ENABLE_DROP.tmp" "$ENABLE_DROP"

systemctl --user daemon-reload
EFFECTIVE="$(systemctl --user show "$SERVICE" -p ExecStartPost --value --no-pager)"
case "$EFFECTIVE" in
  *mio_persona_social_loop_user.py*) ;;
  *) echo 'mio_social_resume=SOCIAL_LOOP_NOT_CONFIGURED'; exit 6 ;;
esac
ENVLINE="$(systemctl --user show "$SERVICE" -p Environment --value --no-pager)"
case "$ENVLINE" in
  *MIO_SOCIAL_AUTO_REPLY_ALLOWED=owner_explicitly_enabled*) ;;
  *) echo 'mio_social_resume=OWNER_FLAG_MISSING'; exit 6 ;;
esac

systemctl --user enable --now "$TIMER" >/dev/null
# Run one cycle now instead of waiting for the next ten-minute timer tick.
systemctl --user start "$SERVICE"
systemctl --user is-active --quiet "$TIMER"

echo 'mio_social_resume=PASS'
echo 'mio_social_discovery=IR_INTEREST_DRIVEN'
echo 'mio_social_reply_decision=IR_REQUIRED'
echo 'mio_social_silence=VALID'
echo 'mio_social_daily_outbound_cap=3'
echo 'mio_social_timer=ACTIVE'

if [ -f "$LOG" ]; then
  tail -n 260 "$LOG" | grep -E '^(mio_persona_ir_|mio_social_loop=|mio_social_decision=|mio_social_publish=|mio_social_outbound=|mio_social_outbound_today=|mio_energy=|mio_life_phase=)' | tail -n 100 || true
fi

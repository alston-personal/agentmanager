#!/usr/bin/env bash
# Owner review boundary for Mio: retain passive monitor timer, remove auto reply.
# Fixed target files only; never publish, run an executor or inspect credentials.
set -euo pipefail
[ "$(id -un)" = ubuntu ] || { echo 'mio_autoreply_pause=WRONG_USER'; exit 2; }
SHA="$(printenv AGENTOS_SOURCE_COMMIT || true)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'mio_autoreply_pause=SOURCE_REQUIRED'; exit 3; }
REPO="$HOME/agentmanager"
UNIT="$HOME/.config/systemd/user/agentos-galaxy-experiment-monitor.service"
TIMER="agentos-galaxy-experiment-monitor.timer"
SERVICE="agentos-galaxy-experiment-monitor.service"
LIVE="$REPO/scripts/mio_persona_social_loop_user.py"
DROP_DIR="$HOME/.config/systemd/user/agentos-galaxy-experiment-monitor.service.d"
DROP="$DROP_DIR/50-owner-review-required.conf"
[ -f "$UNIT" ] && [ -f "$LIVE" ] || {
  echo 'mio_autoreply_pause=MONITOR_NOT_INSTALLED'; exit 3;
}
grep -Fq 'scripts/monitor_galaxy_threads_experiment_user.py' "$UNIT" || {
  echo 'mio_autoreply_pause=READ_ONLY_MONITOR_MISMATCH'; exit 3;
}
grep -Fq 'scripts/mio_persona_social_loop_user.py' "$UNIT" || {
  echo 'mio_autoreply_pause=UNEXPECTED_SERVICE_LAYOUT'; exit 3;
}
STAGED="$LIVE.owner-review-stage"
git -C "$REPO" show "$SHA:scripts/mio_persona_social_loop_user.py" > "$STAGED"
python3 -m py_compile "$STAGED"
grep -Fq "mio_social_loop=OWNER_REVIEW_REQUIRED" "$STAGED" || {
  echo 'mio_autoreply_pause=GUARD_NOT_IN_SOURCE'; exit 3;
}
# Hold new runs while the existing oneshot finishes; do not interrupt a
# possible in-flight Threads write with unknown delivery outcome.
systemctl --user stop "$TIMER"
for _ in $(seq 1 75); do
  if ! systemctl --user is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl --user is-active --quiet "$SERVICE"; then
  echo 'mio_autoreply_pause=WAITING_FOR_EXISTING_RUN_TIMER_STOPPED'
  exit 4
fi
umask 077
mkdir -p "$DROP_DIR"
BACKUP_DIR="$HOME/agent-data/runtime/social/persona/sunlake-milkcat/owner-review-backup"
mkdir -p "$BACKUP_DIR"
if [ ! -f "$BACKUP_DIR/mio_persona_social_loop_user.before-owner-review.py" ]; then
  cp "$LIVE" "$BACKUP_DIR/mio_persona_social_loop_user.before-owner-review.py"
fi
chmod 600 "$BACKUP_DIR/mio_persona_social_loop_user.before-owner-review.py"
chmod 644 "$STAGED"
mv "$STAGED" "$LIVE"
cat > "$DROP.tmp" <<'EOF'
[Service]
# Empty the inherited automatic decision/publish ExecStartPost list.
# Preserve the passive Threads monitor and public observation sync.
ExecStartPost=
ExecStartPost=/bin/sh -c '/usr/bin/python3 /home/ubuntu/agentmanager/scripts/sync_sunlake_milkcat_persona_user.py || echo persona_git_sync=DEFERRED'
EOF
chmod 644 "$DROP.tmp"
mv "$DROP.tmp" "$DROP"
systemctl --user daemon-reload
EFFECTIVE="$(systemctl --user show "$SERVICE" -p ExecStartPost --value --no-pager)"
case "$EFFECTIVE" in
  *mio_persona_social_loop_user.py*)
    echo 'mio_autoreply_pause=AUTOREPLY_STILL_CONFIGURED_TIMER_STOPPED'
    exit 5
    ;;
esac
case "$EFFECTIVE" in
  *sync_sunlake_milkcat_persona_user.py*) ;;
  *) echo 'mio_autoreply_pause=MONITOR_POSTPROCESS_MISMATCH_TIMER_STOPPED'; exit 5 ;;
esac
systemctl --user start "$TIMER"
systemctl --user is-active --quiet "$TIMER" || {
  echo 'mio_autoreply_pause=MONITOR_TIMER_INACTIVE'; exit 6;
}
echo 'mio_autoreply_pause=PASS'
echo 'mio_autoreply_model_decisions=DISABLED'
echo 'mio_autoreply_unreviewed_publishing=DISABLED'
echo 'mio_autoreply_passive_monitor_timer=ACTIVE'
echo 'mio_autoreply_pending_items=PRESERVED'

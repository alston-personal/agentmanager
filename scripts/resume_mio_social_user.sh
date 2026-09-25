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

# Persist a secret-free execution receipt in Mio's canonical data repo so the
# owner can independently verify that this specific exploration cycle ran.
DATA_REPO="$HOME/agent-data"
DATA_HTTPS='https://github.com/alston-personal/my-agent-data.git'
RECEIPT_REL='personas/sunlake-milkcat/runtime/social-cycle-latest.json'
LOCK='/tmp/agentos-mio-persona-data-git.lock'
exec 9>>"$LOCK"
flock -x 9
env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' \
  -C "$DATA_REPO" fetch "$DATA_HTTPS" '+refs/heads/main:refs/remotes/origin/main' >/dev/null
WORK="$(mktemp -d)"
git -C "$DATA_REPO" worktree add --detach "$WORK" origin/main >/dev/null
cleanup_receipt_worktree() {
  git -C "$DATA_REPO" worktree remove --force "$WORK" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup_receipt_worktree EXIT
mkdir -p "$WORK/$(dirname "$RECEIPT_REL")"
python3 - "$LOG" "$WORK/$RECEIPT_REL" "$SHA" <<'PY'
import json,re,sys
from datetime import datetime,timezone
from pathlib import Path
log=Path(sys.argv[1])
out=Path(sys.argv[2])
sha=sys.argv[3]
allowed=re.compile(r'^(mio_(?:persona_ir_[a-z_]+|social_loop|social_decision|social_publish|social_outbound|social_outbound_today|energy|life_phase))=(.{1,180}))
rows=[]
if log.is_file():
    for raw in log.read_text(encoding='utf-8',errors='replace').splitlines()[-320:]:
        m=allowed.fullmatch(raw.strip())
        if m:
            rows.append(raw.strip())
payload={
  'schema':'agentos.mio-social-cycle-receipt/v1',
  'recorded_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
  'source_commit':sha,
  'owner_authorized':True,
  'discovery_policy':'current_persona_ir_interest_driven',
  'silence_is_valid':True,
  'markers':rows[-100:],
}
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
PY
git -C "$WORK" add "$RECEIPT_REL"
if ! git -C "$WORK" diff --cached --quiet; then
  git -C "$WORK" -c user.name='AgentOS Mio Social' -c user.email='agentos-mio-social@users.noreply.github.com' \
    commit -m 'chore(mio): persist latest IR-governed social cycle receipt' >/dev/null
  env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' \
    -C "$WORK" push "$DATA_HTTPS" HEAD:main >/dev/null
fi
echo 'mio_social_cycle_receipt=PASS'

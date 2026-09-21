#!/usr/bin/env bash
# Fixed-purpose ubuntu-owned Mio Telegram deploy. NOT a generic shell carrier.
set -euo pipefail
STAGE=preconditions
trap 'rc=$?; printf "mio_telegram_deploy_stage=%s\nmio_telegram_deploy_exit=%s\n" "$STAGE" "$rc"' ERR
[ "$(id -un)" = ubuntu ] || { echo "mio_telegram_deploy=WRONG_USER"; exit 2; }

LIVE="$HOME/agentmanager"
DATA="$HOME/agent-data"
CAND="$HOME/.local/share/agentos/mio-telegram-candidate"
SHA="$(printenv AGENTOS_SOURCE_COMMIT || true)"
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "mio_telegram_deploy=SOURCE_SHA_REQUIRED"; exit 3;
}
test -d "$LIVE/.git" || { echo "mio_telegram_deploy=LIVE_REPO_MISSING"; exit 3; }
test -s "$HOME/.config/agentos/mio-telegram.env" || {
  echo "mio_telegram_deploy=EXISTING_TOKEN_FILE_MISSING"; exit 3;
}
test -f "$DATA/personas/sunlake-milkcat/character_core.json" || {
  echo "mio_telegram_deploy=PERSONA_IR_MISSING"; exit 3;
}

# Require exact SHA to be on the governed integration branch.
STAGE=fetch_integration
git -C "$LIVE" fetch --quiet --no-tags origin core/integration
LANE="$(git -C "$LIVE" rev-parse FETCH_HEAD)"
STAGE=fetch_source
git -C "$LIVE" fetch --quiet --no-tags origin "$SHA"
test "$(git -C "$LIVE" rev-parse FETCH_HEAD)" = "$SHA" || {
  echo "mio_telegram_deploy=SHA_MISMATCH"; exit 4;
}
git -C "$LIVE" merge-base --is-ancestor "$SHA" "$LANE" || {
  echo "mio_telegram_deploy=UNACCEPTED_SOURCE"; exit 4;
}

STAGE=candidate_checkout
if [ -e "$CAND" ]; then
  test -f "$CAND/.git" || { echo "mio_telegram_deploy=CANDIDATE_INVALID"; exit 4; }
  test -z "$(git -C "$CAND" status --porcelain)" || {
    echo "mio_telegram_deploy=CANDIDATE_DIRTY"; exit 4;
  }
  git -C "$CAND" checkout --quiet --detach "$SHA"
else
  mkdir -p "$(dirname "$CAND")"
  git -C "$LIVE" worktree add --quiet --detach "$CAND" "$SHA"
fi
STAGE=preflight
test "$(git -C "$CAND" rev-parse HEAD)" = "$SHA"
test -f "$CAND/scripts/install_mio_telegram_user.sh"
python3 -m py_compile "$CAND/scripts/mio_telegram_user.py"
bash -n "$CAND/scripts/install_mio_telegram_user.sh"

# Do not pair in unattended deploy or emit a private chat ID.
STAGE=owner_pair_check
grep -Eq '^MIO_TELEGRAM_OWNER_ID=[1-9][0-9]*$' "$HOME/.config/agentos/mio-telegram.env" || {
  echo "mio_telegram_deploy=OWNER_NOT_PAIRED"; exit 5;
}
PRIVATE_LOG="$DATA/runtime/persona/sunlake-milkcat/telegram/deploy-private.log"
mkdir -p "$(dirname "$PRIVATE_LOG")"
chmod 700 "$(dirname "$PRIVATE_LOG")"
umask 077
STAGE=install
AGENTOS_REPO="$CAND" bash "$CAND/scripts/install_mio_telegram_user.sh" > "$PRIVATE_LOG" 2>&1 || {
  echo "mio_telegram_deploy=INSTALL_FAILED"; exit 6;
}
STAGE=services
systemctl --user is-active --quiet agentos-mio-telegram.service || {
  echo "mio_telegram_deploy=SERVICE_INACTIVE"; exit 7;
}
systemctl --user is-active --quiet agentos-mio-agy-relay.service || {
  echo "mio_telegram_deploy=PRIVATE_RELAY_INACTIVE"; exit 7;
}
STAGE=verify
python3 - "$CAND" "$SHA" <<'PY'
import subprocess,sys
from pathlib import Path
candidate, expected = Path(sys.argv[1]), sys.argv[2]
status=subprocess.run(["systemctl","--user","show","agentos-mio-telegram.service",
    "--property=WorkingDirectory","--no-pager"],check=True,text=True,capture_output=True)
assert str(candidate) in status.stdout, "mio_telegram_service_candidate_mismatch"
assert subprocess.check_output(["git","-C",str(candidate),"rev-parse","HEAD"],
    text=True).strip()==expected, "mio_telegram_source_mismatch"
print("mio_telegram_deploy_source_commit="+expected)
print("mio_telegram_deploy=PASS")
PY
# Passive, owner-scoped diagnosis of the last Telegram reply. This does NOT
# create a model task, fetch Telegram updates, or publish private model output.
(cd "$CAND" && PYTHONPATH="$CAND" /usr/bin/python3 - <<'PYSAFE'
from scripts import mio_telegram_user as mio
status = mio.last_status()
reason = status.get("reason")
if reason not in {"ready","working","executor_failed","parse_failed","relay_wait_timeout","context_failed","transport_failed","unknown"}:
    reason = "unknown"
meta = status.get("meta") if isinstance(status.get("meta"), dict) else {}
hint = meta.get("error_hint")
if hint not in {"quota_or_rate","authentication","context_limit","network","permission","timeout","unclassified","unknown"}:
    hint = "unknown"
code = meta.get("returncode")
code = code if type(code) is int and -128 <= code <= 255 else "unknown"
print("mio_telegram_last_status=" + str(reason))
print("mio_telegram_last_error_hint=" + str(hint))
print("mio_telegram_last_exit_code=" + str(code))
PYSAFE

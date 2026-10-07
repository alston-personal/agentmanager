#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_dm_oursong_acceptance=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

TMP="$(mktemp --suffix=.cjs)"
trap 'rm -f "$TMP"' EXIT
git -C "$REPO" show "$SOURCE_COMMIT:scripts/mio_dm_oracle_oursong_acceptance.cjs" > "$TMP"
node --check "$TMP"

set +e
OUT="$(node "$TMP" 2>&1)"
RC=$?
set -e

printf '%s\n' "$OUT" | grep -E '^(mio_dm_oursong_(acceptance|stage|send|readback)=)' || true

if [ "$RC" -ne 0 ]; then
  if printf '%s' "$OUT" | grep -Fq 'mio_dm_oursong_acceptance=LOGIN_REQUIRED'; then
    echo "mio_dm_oursong_stage=session_resume"
    RESUME="$(mktemp --suffix=.sh)"
    git -C "$REPO" show "$SOURCE_COMMIT:scripts/resume_mio_threads_login_user.sh" > "$RESUME"
    chmod 700 "$RESUME"
    set +e
    RESUME_OUT="$(bash "$RESUME" 2>&1)"
    RESUME_RC=$?
    set -e
    rm -f "$RESUME"
    printf '%s\n' "$RESUME_OUT" | grep -E '^threads_mio_login_resume' || true
    if [ "$RESUME_RC" -eq 0 ] && printf '%s\n' "$RESUME_OUT" | grep -Fq 'threads_mio_login_resume=PASS'; then
      set +e
      OUT="$(node "$TMP" 2>&1)"
      RC=$?
      set -e
      printf '%s\n' "$OUT" | grep -E '^(mio_dm_oursong_(acceptance|stage|send|readback)=)' || true
      if [ "$RC" -eq 0 ]; then
        echo "mio_dm_oursong_stage=session_resumed"
        printf '%s\n' "$OUT" | grep -Fq 'mio_dm_oursong_acceptance=PASS'
        printf '%s\n' "$OUT" | grep -Fq 'mio_dm_oursong_readback=PASS'
        exit 0
      fi
    fi
    echo "mio_dm_oursong_stage=session_resume_human_required"
    echo "mio_dm_oursong_acceptance=LOGIN_REQUIRED"
    exit 4
  fi
  if printf '%s' "$OUT" | grep -Fq 'mio_dm_oursong_acceptance=ERROR_CDP_TIMEOUT'; then
    exit 8
  fi
  if printf '%s' "$OUT" | grep -Fq 'mio_dm_oursong_acceptance=ERROR_NODE_WEBSOCKET_UNAVAILABLE'; then
    exit 8
  fi
  exit "$RC"
fi

printf '%s\n' "$OUT" | grep -Fq 'mio_dm_oursong_acceptance=PASS'
printf '%s\n' "$OUT" | grep -Fq 'mio_dm_oursong_readback=PASS'
exit 0

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

set +e
OUT="$(node "$TMP" 2>&1)"
RC=$?
set -e
printf '%s\n' "$OUT" | grep -E '^mio_dm_oursong_(acceptance|stage|send|readback)=' || true
if [ "$RC" -ne 0 ]; then
  if printf '%s' "$OUT" | grep -qi 'playwright'; then
    echo "mio_dm_oursong_acceptance=RUNTIME_PLAYWRIGHT_ERROR"
  elif printf '%s' "$OUT" | grep -qiE 'cdp|127\.0\.0\.1:9222|connect_over_cdp'; then
    echo "mio_dm_oursong_acceptance=RUNTIME_CDP_ERROR"
  else
    echo "mio_dm_oursong_acceptance=RUNTIME_ERROR"
  fi
  exit "$RC"
fi
exit 0

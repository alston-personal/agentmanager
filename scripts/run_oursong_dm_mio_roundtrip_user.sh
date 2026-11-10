#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "oursong_dm_mio_roundtrip=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

TMP="$(mktemp --suffix=.cjs)"
trap 'rm -f "$TMP"' EXIT
git -C "$REPO" show "$SOURCE_COMMIT:scripts/oursong_dm_mio_roundtrip_acceptance.cjs" > "$TMP"
node --check "$TMP"

set +e
OUT="$(node "$TMP" 2>&1)"
RC=$?
set -e

printf '%s
' "$OUT" | grep -E '^(oursong_dm_mio_|mio_dm_oursong_reply_verify=)' || true
exit "$RC"

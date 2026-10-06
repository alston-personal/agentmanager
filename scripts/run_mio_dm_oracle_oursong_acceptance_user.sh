#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_dm_oursong_acceptance=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
git -C "$REPO" show "$SOURCE_COMMIT:scripts/mio_dm_oracle_oursong_acceptance.py" > "$TMP"

PYTHONPATH="$REPO" python3 "$TMP"

#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_observer_project=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
if ! printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "mio_observer_project=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
fi

TMP="$(mktemp)"
git -C "$REPO" show "$SOURCE_COMMIT:scripts/project_mio_observer_user.py" > "$TMP"
chmod 0700 "$TMP"
PYTHONPATH="$REPO" python3 "$TMP"
rm -f "$TMP"

test -s /tmp/mio-observer-public.json
test -s /tmp/mio-observer-owner.json
chmod 0644 /tmp/mio-observer-public.json /tmp/mio-observer-owner.json

echo "mio_observer_project=PASS"

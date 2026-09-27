#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_read=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
if ! printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "threads_web_dm_read=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
fi

for rel in   agentos_node/social/web_dm.py   scripts/threads_web_dm_bridge_user.py; do
  tmp="$(mktemp)"
  git -C "$REPO" show "$SOURCE_COMMIT:$rel" > "$tmp"
  install -D -m 0644 "$tmp" "$REPO/$rel"
  rm -f "$tmp"
done

set +e
OUT="$(PYTHONPATH="$REPO" python3 "$REPO/scripts/threads_web_dm_bridge_user.py" --account mio.milkcat 2>&1)"
RC=$?
set -e
printf '%s
' "$OUT" | grep -E '^threads_web_dm_' || true

if printf '%s
' "$OUT" | grep -Fq 'threads_web_dm_bridge=PASS'; then
  echo "threads_web_dm_read=PASS"
  exit 0
fi
if printf '%s
' "$OUT" | grep -Fq 'threads_web_dm_bridge=LOGIN_REQUIRED'; then
  echo "threads_web_dm_read=LOGIN_REQUIRED"
  exit 0
fi
if printf '%s
' "$OUT" | grep -Fq 'threads_web_dm_bridge=PLAYWRIGHT_UNAVAILABLE'; then
  echo "threads_web_dm_read=PLAYWRIGHT_UNAVAILABLE"
  exit 5
fi

echo "threads_web_dm_read=FAIL"
exit "${RC:-1}"

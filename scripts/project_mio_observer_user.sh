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


LIVE_ACTIVITY="/home/ubuntu/zeus-writer/website/dist/personas/mio/activity.json"
LIVE_DIR="$(dirname "$LIVE_ACTIVITY")"
test -s /tmp/mio-observer-public.json
python3 - <<'PY'
import json
p="/tmp/mio-observer-public.json"
d=json.load(open(p,encoding="utf-8"))
assert d.get("schema")=="milkcat.mio-observer-public/v1", d
assert d.get("updated_at"), d
PY
mkdir -p "$LIVE_DIR"
TMP_LIVE="$LIVE_ACTIVITY.tmp.$$"
cp /tmp/mio-observer-public.json "$TMP_LIVE"
chmod 0644 "$TMP_LIVE"
mv "$TMP_LIVE" "$LIVE_ACTIVITY"
echo "mio_observer_public_live=PASS"

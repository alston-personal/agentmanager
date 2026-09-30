#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "studio_web_mio_deploy=WRONG_USER" >&2
  exit 2
fi

STUDIO_COMMIT="${AGENTOS_STUDIO_COMMIT:-}"
if ! printf '%s' "$STUDIO_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "studio_web_mio_deploy=STUDIO_COMMIT_REQUIRED" >&2
  exit 2
fi

WORK=/home/ubuntu/studio-web-release
LIVE=/home/ubuntu/zeus-writer/website/dist/personas
SRC="$WORK/dist/personas/mio"
DST="$LIVE/mio"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/home/ubuntu/zeus-writer/website/.deploy-backups/mio-$STAMP"

if [ ! -d "$WORK/.git" ]; then
  rm -rf "$WORK"
  gh repo clone alston-personal/studio-web "$WORK"
fi

git -C "$WORK" fetch origin main
git -C "$WORK" checkout --detach "$STUDIO_COMMIT"
git -C "$WORK" reset --hard "$STUDIO_COMMIT"

cd "$WORK"
npm install --no-package-lock --ignore-scripts
npm run build

test -s "$SRC/index.html"
test -s "$SRC/observer/index.html"
test -s "$SRC/activity.json"
grep -Fq '澪的內心窗口' "$SRC/observer/index.html"

mkdir -p "$(dirname "$BACKUP")" "$LIVE"
if [ -d "$DST" ]; then
  cp -a "$DST" "$BACKUP"
fi

TMP="$LIVE/.mio-next-$STAMP"
rm -rf "$TMP"
cp -a "$SRC" "$TMP"
rm -rf "$DST"
mv "$TMP" "$DST"

for i in $(seq 1 20); do
  BODY="$(curl -L -fsS --max-time 15 https://studio.milkcat.org/personas/mio/observer/ || true)"
  if printf '%s' "$BODY" | grep -Fq '澪的內心窗口'; then
    echo "studio_web_mio_public_observer=PASS"
    echo "studio_web_mio_commit=$STUDIO_COMMIT"
    echo "studio_web_mio_backup=$BACKUP"
    echo "studio_web_mio_deploy=PASS"
    exit 0
  fi
  sleep 2
done

if [ -d "$BACKUP" ]; then
  rm -rf "$DST"
  cp -a "$BACKUP" "$DST"
fi

echo "studio_web_mio_public_observer=FAIL" >&2
echo "studio_web_mio_deploy=ROLLED_BACK" >&2
exit 1

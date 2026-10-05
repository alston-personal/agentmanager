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
CURRENT_MAIN="$(git -C "$WORK" rev-parse origin/main)"
if [ "$STUDIO_COMMIT" != "$CURRENT_MAIN" ]; then
  echo "studio_web_mio_deploy=STALE_COMMIT_REFUSED" >&2
  echo "requested_commit=$STUDIO_COMMIT" >&2
  echo "current_main=$CURRENT_MAIN" >&2
  exit 3
fi
git -C "$WORK" checkout --detach "$STUDIO_COMMIT"
git -C "$WORK" reset --hard "$STUDIO_COMMIT"

cd "$WORK"
npm install --no-package-lock --ignore-scripts
npm run build

test -s "$SRC/index.html"
test -s "$SRC/observer/index.html"
test -s "$SRC/activity.json"
test -s "$SRC/wardrobe/index.html"
grep -Fq '澪的內心窗口' "$SRC/observer/index.html"
grep -Fq 'data-tryon-auth-banner' "$SRC/wardrobe/index.html"
grep -Fq '登入／重新授權' "$SRC/wardrobe/index.html"
grep -Fq 'data-tryon-action' "$SRC/wardrobe/index.html"
grep -Fq 'data-mobile-tryon-action' "$SRC/wardrobe/index.html"
grep -Fq '正在等待試穿結果' "$SRC/wardrobe/index.html"
printf '{"studio_commit":"%s","source":"studio-web","bundle":"personas/mio"}\n' "$STUDIO_COMMIT" > "$SRC/release.json"

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
  OBSERVER="$(curl -L -fsS --max-time 15 https://studio.milkcat.org/personas/mio/observer/ || true)"
  WARDROBE="$(curl -L -fsS --max-time 15 https://studio.milkcat.org/personas/mio/wardrobe/ || true)"
  RELEASE="$(curl -L -fsS --max-time 15 https://studio.milkcat.org/personas/mio/release.json || true)"
  if printf '%s' "$OBSERVER" | grep -Fq '澪的內心窗口' \
    && printf '%s' "$WARDROBE" | grep -Fq 'data-tryon-auth-banner' \
    && printf '%s' "$WARDROBE" | grep -Fq '登入／重新授權' \
    && printf '%s' "$WARDROBE" | grep -Fq 'data-tryon-action' \
    && printf '%s' "$RELEASE" | grep -Fq "\"studio_commit\":\"$STUDIO_COMMIT\""; then
    echo "studio_web_mio_public_observer=PASS"
    echo "studio_web_mio_public_wardrobe=PASS"
    echo "studio_web_mio_release_identity=PASS"
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

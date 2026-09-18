#!/usr/bin/env bash
set -euo pipefail

STUDIO_REPO='alston-personal/studio-web'
WORK=$(mktemp -d /tmp/threads-galaxy-deploy.XXXXXX)
TARGET='/home/ubuntu/zeus-writer/website/dist/threads-galaxy'
MIO_TARGET='/home/ubuntu/zeus-writer/website/dist/personas/mio'
BACKUP_ROOT='/home/ubuntu/agent-data/runtime/threads-galaxy-static-backups'
MIO_BACKUP_ROOT='/home/ubuntu/agent-data/runtime/mio-pedigree-static-backups'
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
trap 'rm -rf "$WORK"' EXIT

command -v gh >/dev/null
command -v npm >/dev/null
mkdir -p "$BACKUP_ROOT" "$MIO_BACKUP_ROOT"

echo 'threads_galaxy_static_deploy_scope=single-product'
echo 'threads_galaxy_static_nginx_mutation=NONE'
echo 'threads_galaxy_static_vendor_port=NONE'
echo 'threads_galaxy_static_executor_user='"$(id -un)"
test "$(id -un)" = ubuntu

gh repo clone "$STUDIO_REPO" "$WORK/studio-web" -- --depth=1 --branch main
cd "$WORK/studio-web"
STUDIO_SHA=$(git rev-parse HEAD)
printf '%s' "$STUDIO_SHA" | grep -Eq '^[0-9a-f]{40}$'
echo "threads_galaxy_studio_source_commit=$STUDIO_SHA"

npm install --no-package-lock --ignore-scripts
npm run build
SRC="$WORK/studio-web/dist/threads-galaxy"
MIO_SRC="$WORK/studio-web/dist/personas/mio"
test -s "$SRC/index.html"
test -s "$SRC/app.js"
test -s "$SRC/adapters/threads.js"
test -s "$MIO_SRC/index.html"
grep -Fq '澪' "$MIO_SRC/index.html"
grep -Fq '2026.09.18' "$MIO_SRC/index.html"
grep -Fq '/dashboard/api/social/v1/social' "$SRC/adapters/threads.js"
grep -Fq "PRODUCT_ID='galaxy'" "$SRC/adapters/threads.js"
! grep -RFiq 'X-AgentOS-Product-Key' "$SRC"
! grep -RFiq 'Threads User Access Token' "$SRC"

if [ -d "$TARGET" ]; then
  BACKUP="$BACKUP_ROOT/$STAMP"
  cp -a "$TARGET" "$BACKUP"
  echo "threads_galaxy_static_backup=$BACKUP"
fi

STAGE="${TARGET}.new.$STAMP"
rm -rf "$STAGE"
cp -a "$SRC" "$STAGE"
OLD="${TARGET}.old.$STAMP"
if [ -d "$TARGET" ]; then mv "$TARGET" "$OLD"; fi
mv "$STAGE" "$TARGET"
rm -rf "$OLD"

if [ -d "$MIO_TARGET" ]; then
  MIO_BACKUP="$MIO_BACKUP_ROOT/$STAMP"
  cp -a "$MIO_TARGET" "$MIO_BACKUP"
  echo "mio_pedigree_static_backup=$MIO_BACKUP"
fi
mkdir -p "$(dirname "$MIO_TARGET")"
MIO_STAGE="${MIO_TARGET}.new.$STAMP"
rm -rf "$MIO_STAGE"
cp -a "$MIO_SRC" "$MIO_STAGE"
MIO_OLD="${MIO_TARGET}.old.$STAMP"
if [ -d "$MIO_TARGET" ]; then mv "$MIO_TARGET" "$MIO_OLD"; fi
mv "$MIO_STAGE" "$MIO_TARGET"
rm -rf "$MIO_OLD"

echo "threads_galaxy_static_target=$TARGET"
echo "mio_pedigree_static_target=$MIO_TARGET"
echo 'mio_pedigree_static_deploy=PASS'
echo 'threads_galaxy_static_deploy=PASS'

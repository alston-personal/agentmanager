#!/usr/bin/env bash
set -euo pipefail

STUDIO_REPO='alston-personal/studio-web'
WORK=$(mktemp -d /tmp/threads-galaxy-deploy.XXXXXX)
TARGET='/home/ubuntu/zeus-writer/website/dist/threads-galaxy'
BACKUP_ROOT='/home/ubuntu/agent-data/runtime/threads-galaxy-static-backups'
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
trap 'rm -rf "$WORK"' EXIT

command -v gh >/dev/null
command -v npm >/dev/null
mkdir -p "$BACKUP_ROOT"

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
test -s "$SRC/index.html"
test -s "$SRC/app.js"
test -s "$SRC/adapters/threads.js"
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

echo "threads_galaxy_static_target=$TARGET"
echo 'threads_galaxy_static_deploy=PASS'

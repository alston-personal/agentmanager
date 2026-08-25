#!/usr/bin/env bash
set -euo pipefail

ZEUS=/home/ubuntu/zeus-writer
SOURCE=$ZEUS/website
COMMIT=${LAYOUTLAB_COMMIT:-8dd61bc9664db7867db5d3cdf51da1b0a2162443}
STAGE=${STUDIO_CANDIDATE_ROOT:-/tmp/studio-web-phase1-layoutlab-candidate}
WORK=$STAGE/source
DIST=$WORK/dist
ROOT_DIR=$(pwd)
OUT=$ROOT_DIR/.agentos/evidence/studio-web-phase1-layoutlab-candidate.txt

mkdir -p "$ROOT_DIR/.agentos/evidence"

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "zeus=$ZEUS"
  echo "source=$SOURCE"
  echo "layoutlab_commit=$COMMIT"
  echo '=== SAFETY ==='
  echo 'production_worktree_mutation=NO'
  echo 'production_nginx_mutation=NO'
  echo 'production_service_restart=NO'

  echo '=== FETCH COMMITTED INPUT WITHOUT WORKTREE UPDATE ==='
  git -c safe.directory="$ZEUS" -C "$ZEUS" fetch --no-tags origin master
  if ! git -c safe.directory="$ZEUS" -C "$ZEUS" cat-file -e "$COMMIT^{commit}"; then
    git -c safe.directory="$ZEUS" -C "$ZEUS" fetch --no-tags origin "$COMMIT"
  fi
  git -c safe.directory="$ZEUS" -C "$ZEUS" cat-file -e "$COMMIT^{commit}"
  echo 'layoutlab_commit_object=PASS'

  echo '=== VERIFY COMMITTED INPUT ==='
  changed=$(git -c safe.directory="$ZEUS" -C "$ZEUS" diff-tree --no-commit-id --name-only -r "$COMMIT")
  printf '%s\n' "$changed"
  test "$changed" = 'website/src/pages/layout-lab/index.astro'
  echo 'layoutlab_commit_scope=PASS'

  echo '=== SNAPSHOT LIVE SITE ==='
  rm -rf "$STAGE"
  mkdir -p "$WORK"
  rsync -a \
    --exclude '/node_modules/' \
    --exclude '/.astro/' \
    --exclude '/dist/' \
    --exclude '/.git/' \
    "$SOURCE/" "$WORK/"

  echo '=== OVERLAY COMMITTED LAYOUT LAB PAGE ==='
  mkdir -p "$WORK/src/pages/layout-lab"
  git -c safe.directory="$ZEUS" -C "$ZEUS" show "$COMMIT:website/src/pages/layout-lab/index.astro" > "$WORK/src/pages/layout-lab/index.astro"
  grep -Fq 'title="Layout Lab | Milkcat Studio"' "$WORK/src/pages/layout-lab/index.astro"
  grep -Fq 'Analyze layout' "$WORK/src/pages/layout-lab/index.astro"
  echo "layoutlab_source_sha256=$(sha256sum "$WORK/src/pages/layout-lab/index.astro" | awk '{print $1}')"
  echo 'layoutlab_overlay=PASS'

  echo '=== INDEPENDENT BUILD ==='
  cd "$WORK"
  if [ -f pnpm-lock.yaml ]; then
    if command -v pnpm >/dev/null 2>&1; then pnpm install --frozen-lockfile; pnpm run build;
    else corepack pnpm install --frozen-lockfile; corepack pnpm run build; fi
  elif [ -f package-lock.json ]; then
    npm ci
    npm run build
  else
    echo 'supported_lockfile=MISSING'
    exit 21
  fi
  cd "$ROOT_DIR"

  echo '=== CANDIDATE ACCEPTANCE ==='
  test -s "$DIST/index.html"
  test -s "$DIST/layout-lab/index.html"
  grep -Fq 'Layout Lab | Milkcat Studio' "$DIST/layout-lab/index.html"
  grep -Fq 'Analyze layout' "$DIST/layout-lab/index.html"
  home_sha=$(sha256sum "$DIST/index.html" | awk '{print $1}')
  layout_sha=$(sha256sum "$DIST/layout-lab/index.html" | awk '{print $1}')
  echo "candidate_home_sha256=$home_sha"
  echo "candidate_layoutlab_sha256=$layout_sha"
  test "$home_sha" != "$layout_sha"
  echo 'layoutlab_generated_marker=PASS'
  echo 'layoutlab_distinct_from_home=PASS'

  dep_hits=$(grep -RInE --exclude-dir=node_modules --exclude-dir=.astro --exclude-dir=dist --exclude='*.map' \
    '(/home/ubuntu/zeus-writer|/home/ubuntu/agent-data|\.\./\.\./\.\./)' "$WORK" 2>/dev/null || true)
  if [ -n "$dep_hits" ]; then
    echo "$dep_hits" | head -100
    echo 'independent_runtime_dependency_scan=FAIL'
    exit 22
  fi
  echo 'independent_runtime_dependency_scan=PASS'

  echo '=== PRODUCTION OBSERVATION ==='
  for path in / /layout-lab/; do
    tmp=$(mktemp)
    code=$(curl -L -sS --max-time 15 -o "$tmp" -w '%{http_code}' "https://studio.milkcat.org$path" || true)
    echo "production_path=$path status=$code bytes=$(wc -c < "$tmp") sha256=$(sha256sum "$tmp" | awk '{print $1}')"
    rm -f "$tmp"
  done

  echo 'candidate_mirror_build=PASS'
  echo 'candidate_extraction_readiness=PASS'
  echo 'production_cutover=NO'
} 2>&1 | tee "$OUT"

#!/usr/bin/env bash
set -euo pipefail

ZEUS=/home/ubuntu/zeus-writer
SOURCE=$ZEUS/website
STABLE_LAYOUTLAB_SOURCE=${STABLE_LAYOUTLAB_SOURCE:-$PWD/web_assets/layoutlab_official.html}
EXPECTED_LAYOUTLAB_SHA256=${EXPECTED_LAYOUTLAB_SHA256:-5f24bf9c15dd7cfd36ff0b25166072d5a763998191d2e87f029e651578b95414}
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
  echo "stable_layoutlab_source=$STABLE_LAYOUTLAB_SOURCE"
  echo "expected_layoutlab_sha256=$EXPECTED_LAYOUTLAB_SHA256"
  echo '=== SAFETY ==='
  echo 'production_worktree_mutation=NO'
  echo 'production_nginx_mutation=NO'
  echo 'production_service_restart=NO'

  echo '=== VERIFY STABLE PRODUCTION-ACCEPTED LAYOUT LAB SOURCE ==='
  test -s "$STABLE_LAYOUTLAB_SOURCE"
  grep -Fq '<title>Layout Lab | Milkcat Studio</title>' "$STABLE_LAYOUTLAB_SOURCE"
  grep -Fq 'Analyze layout' "$STABLE_LAYOUTLAB_SOURCE"
  grep -Fq 'Browser engine · LayoutLib v0.1 compatible' "$STABLE_LAYOUTLAB_SOURCE"
  stable_sha=$(sha256sum "$STABLE_LAYOUTLAB_SOURCE" | awk '{print $1}')
  echo "stable_layoutlab_source_sha256=$stable_sha"
  test "$stable_sha" = "$EXPECTED_LAYOUTLAB_SHA256"
  echo 'stable_layoutlab_source_identity=PASS'

  echo '=== SNAPSHOT LIVE SITE ==='
  rm -rf "$STAGE"
  mkdir -p "$WORK"
  rsync -a \
    --exclude '/node_modules/' \
    --exclude '/.astro/' \
    --exclude '/dist/' \
    --exclude '/.git/' \
    "$SOURCE/" "$WORK/"

  echo '=== NORMALIZE LAYOUT LAB OWNERSHIP INTO WEBSITE SOURCE ==='
  if [ -e "$WORK/src/pages/layout-lab" ]; then
    echo 'staged_legacy_layoutlab_route=YES'
    rm -rf "$WORK/src/pages/layout-lab"
  else
    echo 'staged_legacy_layoutlab_route=NO'
  fi
  mkdir -p "$WORK/public/layout-lab"
  cp "$STABLE_LAYOUTLAB_SOURCE" "$WORK/public/layout-lab/index.html"
  copied_sha=$(sha256sum "$WORK/public/layout-lab/index.html" | awk '{print $1}')
  echo "website_owned_layoutlab_source_sha256=$copied_sha"
  test "$copied_sha" = "$EXPECTED_LAYOUTLAB_SHA256"
  echo 'layoutlab_website_ownership_candidate=PASS'

  echo '=== PARENT / ABSOLUTE DEPENDENCY SCAN ==='
  dep_hits=$(grep -RInE --exclude-dir=node_modules --exclude-dir=.astro --exclude-dir=dist --exclude='*.map' \
    '(/home/ubuntu/zeus-writer|/home/ubuntu/agent-data|/home/ubuntu/agentmanager|\.\./\.\./\.\./)' "$WORK" 2>/dev/null || true)
  if [ -n "$dep_hits" ]; then
    echo "$dep_hits" | head -100
    echo 'independent_runtime_dependency_scan=FAIL'
    exit 22
  fi
  echo 'independent_runtime_dependency_scan=PASS'

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
  grep -Fq 'Browser engine · LayoutLib v0.1 compatible' "$DIST/layout-lab/index.html"
  home_sha=$(sha256sum "$DIST/index.html" | awk '{print $1}')
  layout_sha=$(sha256sum "$DIST/layout-lab/index.html" | awk '{print $1}')
  echo "candidate_home_sha256=$home_sha"
  echo "candidate_layoutlab_sha256=$layout_sha"
  test "$layout_sha" = "$EXPECTED_LAYOUTLAB_SHA256"
  test "$home_sha" != "$layout_sha"
  echo 'layoutlab_artifact_identity=PASS'
  echo 'layoutlab_distinct_from_home=PASS'

  echo '=== PRODUCTION OBSERVATION ==='
  prod_layout_sha=''
  for path in / /layout-lab/; do
    tmp=$(mktemp)
    code=$(curl -L -sS --max-time 15 -o "$tmp" -w '%{http_code}' "https://studio.milkcat.org$path" || true)
    sha=$(sha256sum "$tmp" | awk '{print $1}')
    echo "production_path=$path status=$code bytes=$(wc -c < "$tmp") sha256=$sha"
    if [ "$path" = '/layout-lab/' ]; then
      prod_layout_sha=$sha
      test "$code" = 200
      grep -Fq 'Layout Lab' "$tmp"
      grep -Fq 'Analyze layout' "$tmp"
    fi
    rm -f "$tmp"
  done
  if [ "$prod_layout_sha" = "$EXPECTED_LAYOUTLAB_SHA256" ]; then
    echo 'production_layoutlab_matches_verified_asset=PASS'
  else
    echo "production_layoutlab_matches_verified_asset=DRIFT actual=$prod_layout_sha"
  fi

  echo 'candidate_mirror_build=PASS'
  echo 'candidate_extraction_readiness=PASS'
  echo 'production_cutover=NO'
} 2>&1 | tee "$OUT"

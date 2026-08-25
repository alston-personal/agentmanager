#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(pwd)
SOURCE=${STUDIO_SOURCE:-/home/ubuntu/zeus-writer/website}
STAGE=${STUDIO_MIRROR_ROOT:-/tmp/studio-web-phase1-mirror}
WORK="$STAGE/source"
DIST="$WORK/dist"
EVIDENCE=${STUDIO_MIRROR_EVIDENCE:-$ROOT_DIR/.agentos/evidence/studio-web-phase1-mirror.txt}
MANIFEST_DIR=${STUDIO_MIRROR_MANIFEST_DIR:-$ROOT_DIR/.agentos/evidence/studio-web-phase1-manifests}

mkdir -p "$(dirname "$EVIDENCE")" "$MANIFEST_DIR"

hash_tree() {
  local root="$1"
  local out="$2"
  (
    cd "$root"
    find . -type f -print0 | sort -z | xargs -0 -r sha256sum
  ) > "$out"
}

snapshot_source() {
  rm -rf "$STAGE"
  mkdir -p "$WORK"
  rsync -a --delete \
    --exclude '/node_modules/' \
    --exclude '/.astro/' \
    --exclude '/dist/' \
    --exclude '/.git/' \
    "$SOURCE/" "$WORK/"
}

install_and_build() {
  cd "$WORK"
  if [ -f pnpm-lock.yaml ]; then
    command -v corepack >/dev/null 2>&1 && corepack enable >/dev/null 2>&1 || true
    if command -v pnpm >/dev/null 2>&1; then
      pnpm install --frozen-lockfile
      pnpm run build
    else
      corepack pnpm install --frozen-lockfile
      corepack pnpm run build
    fi
  elif [ -f package-lock.json ]; then
    npm ci
    npm run build
  elif [ -f yarn.lock ]; then
    command -v corepack >/dev/null 2>&1 && corepack enable >/dev/null 2>&1 || true
    corepack yarn install --immutable
    corepack yarn build
  else
    echo 'ERROR: no supported lockfile found; refusing non-reproducible install' >&2
    return 21
  fi
  cd "$ROOT_DIR"
}

probe_file() {
  local rel="$1"
  local file="$DIST/$rel"
  if [ ! -s "$file" ]; then
    echo "mirror_file=$rel exists=NO"
    return 1
  fi
  local bytes sha
  bytes=$(wc -c < "$file")
  sha=$(sha256sum "$file" | awk '{print $1}')
  echo "mirror_file=$rel exists=YES bytes=$bytes sha256=$sha"
}

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "source=$SOURCE"
  echo "stage=$STAGE"
  echo "evidence=$EVIDENCE"
  echo "manifest_dir=$MANIFEST_DIR"

  echo '=== SAFETY PRECONDITIONS ==='
  test -d "$SOURCE"
  test -f "$SOURCE/package.json"
  case "$STAGE" in
    /tmp/*|/home/agentos-node/*) ;;
    *) echo "ERROR: unsafe staging root: $STAGE"; exit 20 ;;
  esac
  echo 'production_nginx_mutation=NO'
  echo 'production_repo_reset=NO'
  echo 'production_repo_clean=NO'
  echo 'production_service_restart=NO'

  echo '=== LIVE SOURCE OBSERVATION ==='
  stat -c 'source_stat=%U:%G %a %F %n' "$SOURCE"
  printf 'lockfiles='
  find "$SOURCE" -maxdepth 1 -type f \( -name 'pnpm-lock.yaml' -o -name 'package-lock.json' -o -name 'yarn.lock' \) -printf '%f ' | sort
  echo
  if [ -d /home/ubuntu/zeus-writer/.git ]; then
    git -c safe.directory=/home/ubuntu/zeus-writer -C /home/ubuntu/zeus-writer status --short -- website | head -200 || true
  fi

  echo '=== SNAPSHOT ==='
  snapshot_source
  test -f "$WORK/package.json"
  hash_tree "$WORK" "$MANIFEST_DIR/source-before-build.sha256"
  echo "source_manifest_files=$(wc -l < "$MANIFEST_DIR/source-before-build.sha256")"
  echo "source_manifest_sha256=$(sha256sum "$MANIFEST_DIR/source-before-build.sha256" | awk '{print $1}')"

  echo '=== PARENT / ABSOLUTE DEPENDENCY SCAN ==='
  dep_hits=$(grep -RInE --exclude-dir=node_modules --exclude-dir=.astro --exclude-dir=dist --exclude='*.map' \
    '(/home/ubuntu/zeus-writer|/home/ubuntu/agent-data|\.\./\.\./\.\./)' "$WORK" 2>/dev/null || true)
  if [ -n "$dep_hits" ]; then
    echo "$dep_hits" | head -200
    echo 'independent_runtime_dependency_scan=FAIL'
  else
    echo 'independent_runtime_dependency_scan=PASS'
  fi

  echo '=== INDEPENDENT INSTALL + BUILD ==='
  install_and_build
  test -s "$DIST/index.html"
  hash_tree "$DIST" "$MANIFEST_DIR/dist.sha256"
  echo "dist_manifest_files=$(wc -l < "$MANIFEST_DIR/dist.sha256")"
  echo "dist_manifest_sha256=$(sha256sum "$MANIFEST_DIR/dist.sha256" | awk '{print $1}')"

  echo '=== MIRROR ROUTE ARTIFACTS ==='
  probe_file index.html
  for rel in \
    novels/index.html \
    layout-lab/index.html \
    agentos/index.html \
    tiandao/index.html \
    testimony/index.html \
    translator/index.html \
    language-notes/index.html \
    omnirealm/index.html \
    tech-notes/index.html; do
    probe_file "$rel" || true
  done

  echo '=== LAYOUT LAB REGRESSION GUARD ==='
  layout_ok=0
  if [ -s "$DIST/layout-lab/index.html" ]; then
    if grep -Eqi 'Layout Lab|Analyze layout|layout.?lab' "$DIST/layout-lab/index.html"; then
      echo 'layout_lab_generated_marker=PASS'
      layout_ok=1
    else
      echo 'layout_lab_generated_marker=FAIL'
    fi
  else
    echo 'layout_lab_generated_artifact=MISSING'
  fi
  home_sha=$(sha256sum "$DIST/index.html" | awk '{print $1}')
  if [ -s "$DIST/layout-lab/index.html" ]; then
    layout_sha=$(sha256sum "$DIST/layout-lab/index.html" | awk '{print $1}')
    echo "home_sha256=$home_sha"
    echo "layout_lab_sha256=$layout_sha"
    if [ "$home_sha" = "$layout_sha" ]; then
      echo 'layout_lab_distinct_from_home=FAIL'
      layout_ok=0
    else
      echo 'layout_lab_distinct_from_home=PASS'
    fi
  fi

  echo '=== PRODUCTION READ-ONLY REFERENCE ==='
  for path in / /dashboard /layout-lab/ /prophecy/ /novels/ /ipgenome /iftv /echo /hanzi /acas/; do
    tmp=$(mktemp)
    code=$(curl -L -sS --max-time 15 -o "$tmp" -w '%{http_code}' "https://studio.milkcat.org$path" || true)
    bytes=$(wc -c < "$tmp" 2>/dev/null || echo 0)
    sha=$(sha256sum "$tmp" 2>/dev/null | awk '{print $1}')
    echo "production_path=$path status=$code bytes=$bytes body_sha256=$sha"
    rm -f "$tmp"
  done

  echo '=== PHASE 1 RESULT ==='
  echo 'mirror_build=PASS'
  if [ "$layout_ok" -eq 1 ] && [ -z "$dep_hits" ]; then
    echo 'phase1_extraction_readiness=PASS'
  else
    echo 'phase1_extraction_readiness=NO_GO'
  fi
  echo 'cutover=NO'
} 2>&1 | tee "$EVIDENCE"

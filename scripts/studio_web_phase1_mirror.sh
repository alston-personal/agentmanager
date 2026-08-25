#!/usr/bin/env bash
set -euo pipefail

SOURCE=${STUDIO_SOURCE:-/home/ubuntu/zeus-writer/website}
STAGE=${STUDIO_MIRROR_ROOT:-/tmp/studio-web-phase1-mirror}
WORK="$STAGE/source"
DIST="$WORK/dist"
EVIDENCE=${STUDIO_MIRROR_EVIDENCE:-.agentos/evidence/studio-web-phase1-mirror.txt}
MANIFEST_DIR=${STUDIO_MIRROR_MANIFEST_DIR:-.agentos/evidence/studio-web-phase1-manifests}

mkdir -p "$(dirname "$EVIDENCE")" "$MANIFEST_DIR"

hash_tree() {
  local root="$1"
  local out="$2"
  (
    cd "$root"
    find . -type f -print0 \
      | sort -z \
      | xargs -0 -r sha256sum
  ) > "$out"
}

snapshot_source() {
  rm -rf "$STAGE"
  mkdir -p "$WORK"
  # The live Zeus Writer checkout is intentionally treated as source-of-observed
  # truth for Phase 1. Do not git reset/clean it: production-significant content
  # may currently be modified or untracked.
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
    echo 'ERROR: no supported lockfile found; refusing non-reproducible npm install' >&2
    return 21
  fi
}

probe_file() {
  local rel="$1"
  local marker="$2"
  local file="$DIST/$rel"
  if [ ! -s "$file" ]; then
    echo "mirror_file=$rel exists=NO marker=$marker"
    return 1
  fi
  local bytes sha
  bytes=$(wc -c < "$file")
  sha=$(sha256sum "$file" | awk '{print $1}')
  echo "mirror_file=$rel exists=YES bytes=$bytes sha256=$sha marker=$marker"
  if [ -n "$marker" ]; then
    grep -Fq "$marker" "$file"
  fi
}

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "source=$SOURCE"
  echo "stage=$STAGE"

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

  echo '=== INDEPENDENT INSTALL + BUILD ==='
  install_and_build
  test -s "$DIST/index.html"
  hash_tree "$DIST" "$MANIFEST_DIR/dist.sha256"
  echo "dist_manifest_files=$(wc -l < "$MANIFEST_DIR/dist.sha256")"
  echo "dist_manifest_sha256=$(sha256sum "$MANIFEST_DIR/dist.sha256" | awk '{print $1}')"

  echo '=== MIRROR ROUTE ARTIFACTS ==='
  probe_file index.html ''
  # These probes intentionally distinguish a real generated page from nginx
  # fallback HTML. Missing artifacts are evidence, not silently accepted.
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
    if [ -e "$DIST/$rel" ]; then
      probe_file "$rel" '' || true
    else
      echo "mirror_file=$rel exists=NO"
    fi
  done

  echo '=== LAYOUT LAB REGRESSION GUARD ==='
  if [ -s "$DIST/layout-lab/index.html" ]; then
    if grep -Eq 'Layout Lab|Analyze layout' "$DIST/layout-lab/index.html"; then
      echo 'layout_lab_generated_marker=PASS'
    else
      echo 'layout_lab_generated_marker=FAIL'
    fi
  else
    echo 'layout_lab_generated_artifact=MISSING'
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
  echo 'cutover=NO'
} 2>&1 | tee "$EVIDENCE"

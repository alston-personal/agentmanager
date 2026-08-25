#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(pwd)
EVIDENCE=${STUDIO_CANDIDATE_EVIDENCE:-$ROOT_DIR/.agentos/evidence/studio-web-phase1-layoutlab-candidate.txt}
SOURCE=${STUDIO_SOURCE:-/home/ubuntu/zeus-writer/website}
TARGET=${STUDIO_WEB_TARGET:-/home/agentos-node/projects/studio-web}
STABLE_LAYOUTLAB_SOURCE=${STABLE_LAYOUTLAB_SOURCE:-$ROOT_DIR/web_assets/layoutlab_official.html}
EXPECTED_LAYOUTLAB_SHA256=${EXPECTED_LAYOUTLAB_SHA256:-5f24bf9c15dd7cfd36ff0b25166072d5a763998191d2e87f029e651578b95414}
OUT=$ROOT_DIR/.agentos/evidence/studio-web-parallel-checkout.txt

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "source=$SOURCE"
  echo "target=$TARGET"
  echo "stable_layoutlab_source=$STABLE_LAYOUTLAB_SOURCE"
  echo "expected_layoutlab_sha256=$EXPECTED_LAYOUTLAB_SHA256"

  echo '=== GATE ==='
  test -f "$EVIDENCE"
  grep -Fxq 'candidate_mirror_build=PASS' "$EVIDENCE"
  grep -Fxq 'candidate_extraction_readiness=PASS' "$EVIDENCE"
  grep -Fxq 'production_cutover=NO' "$EVIDENCE"
  grep -Fxq 'production_layoutlab_matches_verified_asset=PASS' "$EVIDENCE"
  echo 'candidate_gate=PASS'

  echo '=== SAFETY ==='
  case "$TARGET" in
    /home/agentos-node/projects/studio-web|/home/ubuntu/studio-web) ;;
    *) echo "unsafe_target=$TARGET"; exit 20;;
  esac
  echo 'nginx_mutation=NO'
  echo 'resource_registry_mutation=NO'
  echo 'action_relay_site_owner_mutation=NO'
  echo 'production_service_restart=NO'
  echo 'production_cutover=NO'

  echo '=== VERIFY WEBSITE-OWNED LAYOUT LAB INPUT ==='
  test -s "$STABLE_LAYOUTLAB_SOURCE"
  stable_sha=$(sha256sum "$STABLE_LAYOUTLAB_SOURCE" | awk '{print $1}')
  echo "stable_layoutlab_source_sha256=$stable_sha"
  test "$stable_sha" = "$EXPECTED_LAYOUTLAB_SHA256"
  grep -Fq '<title>Layout Lab | Milkcat Studio</title>' "$STABLE_LAYOUTLAB_SOURCE"
  grep -Fq 'Analyze layout' "$STABLE_LAYOUTLAB_SOURCE"
  grep -Fq 'Browser engine · LayoutLib v0.1 compatible' "$STABLE_LAYOUTLAB_SOURCE"
  echo 'stable_layoutlab_source_identity=PASS'

  echo '=== TARGET PRECONDITION ==='
  if [ -e "$TARGET" ]; then
    if [ -d "$TARGET/.git" ]; then
      echo 'target_existing_git=YES'
      dirty=$(git -c safe.directory="$TARGET" -C "$TARGET" status --porcelain || true)
      if [ -n "$dirty" ]; then
        echo 'ERROR: existing studio-web checkout is dirty; refusing overwrite'
        exit 21
      fi
      echo 'ERROR: target already initialized; use an explicit update workflow instead'
      exit 22
    fi
    if [ -n "$(find "$TARGET" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
      echo 'ERROR: target exists and is non-empty'
      exit 23
    fi
  fi

  echo '=== SNAPSHOT LIVE PLATFORM SOURCE ==='
  rm -rf "$TARGET.tmp"
  mkdir -p "$TARGET.tmp"
  rsync -a \
    --exclude '/node_modules/' \
    --exclude '/.astro/' \
    --exclude '/dist/' \
    --exclude '/.git/' \
    "$SOURCE/" "$TARGET.tmp/"

  echo '=== NORMALIZE LAYOUT LAB INTO WEBSITE SOURCE OWNERSHIP ==='
  if [ -e "$TARGET.tmp/src/pages/layout-lab" ]; then
    echo 'staged_legacy_layoutlab_route=YES'
    rm -rf "$TARGET.tmp/src/pages/layout-lab"
  else
    echo 'staged_legacy_layoutlab_route=NO'
  fi
  mkdir -p "$TARGET.tmp/public/layout-lab"
  cp "$STABLE_LAYOUTLAB_SOURCE" "$TARGET.tmp/public/layout-lab/index.html"
  copied_sha=$(sha256sum "$TARGET.tmp/public/layout-lab/index.html" | awk '{print $1}')
  echo "website_owned_layoutlab_source_sha256=$copied_sha"
  test "$copied_sha" = "$EXPECTED_LAYOUTLAB_SHA256"

  echo '=== INDEPENDENCE SCAN ==='
  dep_hits=$(grep -RInE --exclude-dir=node_modules --exclude-dir=.astro --exclude-dir=dist --exclude='*.map' \
    '(/home/ubuntu/zeus-writer|/home/ubuntu/agent-data|/home/ubuntu/agentmanager|\.\./\.\./\.\./)' "$TARGET.tmp" 2>/dev/null || true)
  if [ -n "$dep_hits" ]; then
    echo "$dep_hits" | head -100
    echo 'independent_runtime_dependency_scan=FAIL'
    exit 25
  fi
  echo 'independent_runtime_dependency_scan=PASS'

  echo '=== PROVENANCE ==='
  source_manifest=$(cd "$TARGET.tmp" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | awk '{print $1}')
  cat > "$TARGET.tmp/STUDIO_WEB_PROVENANCE.md" <<EOF
# Studio Web Extraction Provenance

- extracted_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- observed_live_source: $SOURCE
- candidate_snapshot_manifest: $source_manifest
- layout_lab_verified_asset_sha256: $EXPECTED_LAYOUTLAB_SHA256
- layout_lab_source_migration_from: agentmanager/web_assets/layoutlab_official.html
- layout_lab_source_migration_to: public/layout-lab/index.html
- production_cutover_performed: no

The independent source tree is based on the observed live Studio Web filesystem, including live modified/untracked website content. The production-accepted browser-only Layout Lab asset is moved into the website source tree so future builds no longer require an AgentOS post-build write into another product repository.
EOF

  echo '=== INDEPENDENT GIT INIT ==='
  git -C "$TARGET.tmp" init -b main
  git -C "$TARGET.tmp" config user.name 'AgentOS Migration'
  git -C "$TARGET.tmp" config user.email 'agentos@local.invalid'
  git -C "$TARGET.tmp" add -A
  git -C "$TARGET.tmp" commit -m 'chore: extract Studio Web platform source'
  initial_sha=$(git -C "$TARGET.tmp" rev-parse HEAD)
  mkdir -p "$(dirname "$TARGET")"
  mv "$TARGET.tmp" "$TARGET"
  echo "studio_web_initial_sha=$initial_sha"

  echo '=== CLEAN BUILD ACCEPTANCE ==='
  cd "$TARGET"
  if [ -f pnpm-lock.yaml ]; then
    if command -v pnpm >/dev/null 2>&1; then pnpm install --frozen-lockfile; pnpm run build;
    else corepack pnpm install --frozen-lockfile; corepack pnpm run build; fi
  elif [ -f package-lock.json ]; then
    npm ci
    npm run build
  else
    echo 'ERROR: no supported lockfile'
    exit 24
  fi
  test -s dist/index.html
  test -s dist/layout-lab/index.html
  grep -Fq 'Layout Lab | Milkcat Studio' dist/layout-lab/index.html
  grep -Fq 'Analyze layout' dist/layout-lab/index.html
  grep -Fq 'Browser engine · LayoutLib v0.1 compatible' dist/layout-lab/index.html
  layout_sha=$(sha256sum dist/layout-lab/index.html | awk '{print $1}')
  home_sha=$(sha256sum dist/index.html | awk '{print $1}')
  echo "parallel_layoutlab_sha256=$layout_sha"
  echo "parallel_home_sha256=$home_sha"
  test "$layout_sha" = "$EXPECTED_LAYOUTLAB_SHA256"
  test "$home_sha" != "$layout_sha"
  cd "$ROOT_DIR"

  echo 'parallel_checkout_clean_build=PASS'
  echo 'layoutlab_website_owned=PASS'
  echo 'production_cutover=NO'
  echo 'studio_web_parallel_checkout=PASS'
} 2>&1 | tee "$OUT"

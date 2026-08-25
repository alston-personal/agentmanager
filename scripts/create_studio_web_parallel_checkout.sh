#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(pwd)
EVIDENCE=${STUDIO_CANDIDATE_EVIDENCE:-$ROOT_DIR/.agentos/evidence/studio-web-phase1-layoutlab-candidate.txt}
ZEUS=${ZEUS_ROOT:-/home/ubuntu/zeus-writer}
SOURCE=${STUDIO_SOURCE:-$ZEUS/website}
TARGET=${STUDIO_WEB_TARGET:-/home/ubuntu/studio-web}
LAYOUT_COMMIT=${LAYOUTLAB_COMMIT:-8dd61bc9664db7867db5d3cdf51da1b0a2162443}
OUT=$ROOT_DIR/.agentos/evidence/studio-web-parallel-checkout.txt

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_identity=$(id)"
  echo "source=$SOURCE"
  echo "target=$TARGET"
  echo "layoutlab_commit=$LAYOUT_COMMIT"

  echo '=== GATE ==='
  test -f "$EVIDENCE"
  grep -Fxq 'candidate_mirror_build=PASS' "$EVIDENCE"
  grep -Fxq 'candidate_extraction_readiness=PASS' "$EVIDENCE"
  grep -Fxq 'production_cutover=NO' "$EVIDENCE"
  echo 'candidate_gate=PASS'

  echo '=== SAFETY ==='
  case "$TARGET" in /home/ubuntu/studio-web) ;; *) echo "unsafe_target=$TARGET"; exit 20;; esac
  echo 'nginx_mutation=NO'
  echo 'resource_registry_mutation=NO'
  echo 'action_relay_site_owner_mutation=NO'
  echo 'production_service_restart=NO'

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

  echo '=== OVERLAY COMMITTED LAYOUT LAB ==='
  mkdir -p "$TARGET.tmp/src/pages/layout-lab"
  git -c safe.directory="$ZEUS" -C "$ZEUS" show "$LAYOUT_COMMIT:website/src/pages/layout-lab/index.astro" > "$TARGET.tmp/src/pages/layout-lab/index.astro"
  grep -Fq 'Layout Lab | Milkcat Studio' "$TARGET.tmp/src/pages/layout-lab/index.astro"
  grep -Fq 'Analyze layout' "$TARGET.tmp/src/pages/layout-lab/index.astro"

  echo '=== PROVENANCE ==='
  source_manifest=$(cd "$TARGET.tmp" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | awk '{print $1}')
  zeus_head=$(git -c safe.directory="$ZEUS" -C "$ZEUS" rev-parse HEAD)
  cat > "$TARGET.tmp/STUDIO_WEB_PROVENANCE.md" <<EOF
# Studio Web Extraction Provenance

- extracted_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- live_source: $SOURCE
- live_zeus_head: $zeus_head
- phase1_live_source_manifest: e4702569176d7e378f4be3154bee3cb7384bcc605b60743474585780dc804e69
- candidate_snapshot_manifest: $source_manifest
- layout_lab_source_commit: $LAYOUT_COMMIT
- production_cutover_performed: no

The initial independent tree is intentionally based on the observed live website filesystem, including live modified/untracked website content, plus the committed Layout Lab platform page that was present in Zeus Writer history but absent from the live checkout at audit time.
EOF

  echo '=== INDEPENDENT GIT INIT ==='
  git -C "$TARGET.tmp" init -b main
  git -C "$TARGET.tmp" config user.name 'AgentOS Migration'
  git -C "$TARGET.tmp" config user.email 'agentos@local.invalid'
  git -C "$TARGET.tmp" add -A
  git -C "$TARGET.tmp" commit -m 'chore: extract Studio Web platform source'
  initial_sha=$(git -C "$TARGET.tmp" rev-parse HEAD)
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
  test "$(sha256sum dist/index.html | awk '{print $1}')" != "$(sha256sum dist/layout-lab/index.html | awk '{print $1}')"
  cd "$ROOT_DIR"
  echo 'parallel_checkout_clean_build=PASS'
  echo 'production_cutover=NO'
  echo 'studio_web_parallel_checkout=PASS'
} 2>&1 | tee "$OUT"

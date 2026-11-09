#!/usr/bin/env bash
set -euo pipefail

ROOT="${LEGACY_DASHBOARD_RELEASE_ROOT:-/home/ubuntu/agent-data/releases/dashboard}"
APPS="$ROOT/apps"
RUNTIME_ROOT="${DASHBOARD_RUNTIME_ROOT:-/home/ubuntu/agent-data/runtime/dashboard}"
KEEP_APPS="${LEGACY_DASHBOARD_KEEP_APPS:-4}"
KEEP_USAGE="${LEGACY_DASHBOARD_KEEP_USAGE:-2}"

[[ "$KEEP_APPS" =~ ^[0-9]+$ ]]
[[ "$KEEP_USAGE" =~ ^[0-9]+$ ]]
[ "$KEEP_APPS" -ge 1 ]
[ -d "$ROOT" ]

exec 9>/tmp/agentos-dashboard-deploy.lock
flock -w 360 9

echo '=== legacy dashboard retention before ==='
df -h /

if [ -d "$APPS" ]; then
  keep_file="$(mktemp)"
  trap 'rm -f "$keep_file"' EXIT

  if [ -L "$RUNTIME_ROOT/current" ]; then
    target="$(readlink -f "$RUNTIME_ROOT/current" 2>/dev/null || true)"
    case "$target" in
      "$APPS"/*) basename "$target" >> "$keep_file" ;;
    esac
  fi

  for proc in /proc/[0-9]*; do
    cwd="$(readlink -f "$proc/cwd" 2>/dev/null || true)"
    case "$cwd" in
      "$APPS"/*)
        rel="${cwd#"$APPS"/}"
        printf '%s\n' "${rel%%/*}" >> "$keep_file"
        ;;
    esac
  done

  find "$APPS" -mindepth 1 -maxdepth 1 -type d -printf '%T@\t%f\n' 2>/dev/null |
    sort -nr | head -n "$KEEP_APPS" | cut -f2- >> "$keep_file" || true
  sort -u -o "$keep_file" "$keep_file"

  echo '=== legacy dashboard apps keep set ==='
  cat "$keep_file"

  removed_apps=0
  while IFS= read -r -d '' dir; do
    name="$(basename "$dir")"
    if grep -Fxq "$name" "$keep_file"; then
      continue
    fi
    echo "prune_legacy_app=$dir"
    rm -rf --one-file-system -- "$dir"
    removed_apps=$((removed_apps + 1))
  done < <(find "$APPS" -mindepth 1 -maxdepth 1 -type d -print0)

  if [ -L "$RUNTIME_ROOT/current" ]; then
    target="$(readlink -f "$RUNTIME_ROOT/current")"
    [ -d "$target" ] || {
      echo "ERROR: legacy current runtime target missing: $target" >&2
      exit 42
    }
  fi
  echo "removed_legacy_app_dirs=$removed_apps"
fi

mapfile -t usage_keep < <(
  find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name 'usage-*' -printf '%T@\t%p\n' 2>/dev/null |
    sort -nr | head -n "$KEEP_USAGE" | cut -f2-
)
removed_usage=0
while IFS= read -r -d '' dir; do
  keep=0
  for k in "${usage_keep[@]}"; do
    [ "$dir" = "$k" ] && keep=1 && break
  done
  [ "$keep" = 1 ] && continue
  echo "prune_legacy_usage=$dir"
  rm -rf --one-file-system -- "$dir"
  removed_usage=$((removed_usage + 1))
done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name 'usage-*' -print0)

echo "removed_legacy_usage_dirs=$removed_usage"
echo '=== legacy dashboard retention after ==='
df -h /
echo 'legacy_dashboard_release_retention=PASS'

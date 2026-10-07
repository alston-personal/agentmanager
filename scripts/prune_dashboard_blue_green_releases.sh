#!/usr/bin/env bash
set -euo pipefail

ROOT="${DASHBOARD_RELEASE_ROOT:-/home/ubuntu/agent-data/releases/dashboard-blue-green}"
RUNTIME_ROOT="${DASHBOARD_RUNTIME_ROOT:-/home/ubuntu/agent-data/runtime/dashboard}"
KEEP_NEWEST="${DASHBOARD_RELEASE_KEEP_NEWEST:-6}"

[[ "$KEEP_NEWEST" =~ ^[0-9]+$ ]]
[ "$KEEP_NEWEST" -ge 2 ]
[ -d "$ROOT" ]

if [ "${DASHBOARD_RETENTION_LOCK_HELD:-0}" != "1" ]; then
  exec 9>/tmp/agentos-dashboard-deploy.lock
  flock -w 360 9
fi

keep_file="$(mktemp)"
trap 'rm -f "$keep_file"' EXIT

keep_release() {
  local target="$1"
  case "$target" in
    "$ROOT"/*)
      basename "$target" >> "$keep_file"
      ;;
  esac
}

for slot in blue green; do
  if [ -L "$RUNTIME_ROOT/$slot" ]; then
    keep_release "$(readlink -f "$RUNTIME_ROOT/$slot" 2>/dev/null || true)"
  fi
done

for proc in /proc/[0-9]*; do
  cwd="$(readlink -f "$proc/cwd" 2>/dev/null || true)"
  case "$cwd" in
    "$ROOT"/*)
      rel="${cwd#"$ROOT"/}"
      printf '%s\n' "${rel%%/*}" >> "$keep_file"
      ;;
  esac
done

find "$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@\t%f\n' 2>/dev/null |
  sort -nr |
  head -n "$KEEP_NEWEST" |
  cut -f2- >> "$keep_file" || true

sort -u -o "$keep_file" "$keep_file"

echo '=== dashboard release retention keep set ==='
cat "$keep_file"
echo '=== before ==='
df -h /
printf 'release_dirs_before='
find "$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '.\n' | wc -l

removed=0
while IFS= read -r -d '' dir; do
  name="$(basename "$dir")"
  if grep -Fxq "$name" "$keep_file"; then
    continue
  fi
  echo "prune_release=$dir"
  rm -rf --one-file-system -- "$dir"
  removed=$((removed + 1))
done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -print0)

for slot in blue green; do
  if [ -L "$RUNTIME_ROOT/$slot" ]; then
    target="$(readlink -f "$RUNTIME_ROOT/$slot")"
    [ -d "$target" ] || {
      echo "ERROR: retained runtime target missing: $slot -> $target" >&2
      exit 42
    }
  fi
done

echo "removed_release_dirs=$removed"
printf 'release_dirs_after='
find "$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '.\n' | wc -l
echo '=== after ==='
df -h /
echo 'dashboard_release_retention=PASS'

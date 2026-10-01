#!/usr/bin/env bash
set -euo pipefail

MOUNTPOINT="${AGENTOS_GDRIVE_MOUNTPOINT:-/home/ubuntu/gdrive}"
REMOTE="${AGENTOS_GDRIVE_REMOTE:-gdrive:}"

fail() {
  echo "FATAL: $*" >&2
  exit 70
}

command -v mountpoint >/dev/null 2>&1 || fail "mountpoint command unavailable"
command -v rclone >/dev/null 2>&1 || fail "rclone unavailable"

mountpoint -q "$MOUNTPOINT" || fail "$MOUNTPOINT is not mounted; refusing to write into local underlay"

fs_type="$(findmnt -n -o FSTYPE --target "$MOUNTPOINT" 2>/dev/null || true)"
case "$fs_type" in
  fuse.rclone|fuse)
    ;;
  *)
    fail "$MOUNTPOINT is mounted with unexpected filesystem type: ${fs_type:-unknown}"
    ;;
esac

rclone lsd "$REMOTE" >/dev/null 2>&1 || fail "rclone remote $REMOTE is not reachable"

echo "gdrive_guard=PASS mountpoint=$MOUNTPOINT fstype=$fs_type remote=$REMOTE"

#!/usr/bin/env bash
set -euo pipefail

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
MOUNTPOINT="${AGENTOS_GDRIVE_MOUNTPOINT:-/home/ubuntu/gdrive}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 77
fi

command -v rclone >/dev/null 2>&1 || { echo "rclone is required" >&2; exit 69; }
test -f /home/ubuntu/.config/rclone/rclone.conf || {
  echo "Missing /home/ubuntu/.config/rclone/rclone.conf" >&2
  exit 66
}

if mountpoint -q "$MOUNTPOINT"; then
  echo "Current mount detected at $MOUNTPOINT."
else
  if find "$MOUNTPOINT" -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
    echo "REFUSING INSTALL: local underlay at $MOUNTPOINT is not empty." >&2
    echo "Run scripts/oracle_gdrive_recovery_audit.sh and recover local-only files first." >&2
    exit 65
  fi
fi

install -Dm0644 "$REPO/ops/storage/agentos-gdrive-rclone.service"   /etc/systemd/system/agentos-gdrive-rclone.service
install -Dm0644 "$REPO/ops/storage/agentos-storage-ready.service"   /etc/systemd/system/agentos-storage-ready.service
chmod +x "$REPO/scripts/oracle_gdrive_guard.sh" "$REPO/scripts/oracle_gdrive_recovery_audit.sh"

systemctl daemon-reload
systemctl enable agentos-gdrive-rclone.service agentos-storage-ready.service
systemctl restart agentos-gdrive-rclone.service
systemctl restart agentos-storage-ready.service

sudo -u ubuntu "$REPO/scripts/oracle_gdrive_guard.sh"
echo "oracle_gdrive_install=PASS"

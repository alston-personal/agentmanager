#!/usr/bin/env bash
# AgentOS #1682 / Oracle Google Drive read-only acceptance; no remediation.
set -uo pipefail
export LC_ALL=C
CANONICAL="${HOME}/.local/share/agentos/gdrive-remote-v2"
LEGACY="${HOME}/gdrive"
STATE="${HOME}/.local/state/agentos/gdrive-health.state"
LOG="${HOME}/agent-data/logs/action-relay-reconcile.log"
failed=0
emit(){ printf '%s=%s\n' "$1" "$2"; }
fail(){ emit "$1" FAIL; failed=1; }
pass(){ emit "$1" PASS; }
check_mount(){
  if mountpoint -q -- "$CANONICAL" && [[ "$(findmnt -rn -o FSTYPE -T "$CANONICAL" 2>/dev/null)" == fuse.rclone ]]; then pass gdrive_fuse_mount; else fail gdrive_fuse_mount; fi
}
check_legacy(){
  if [[ -L "$LEGACY" && "$(readlink -f -- "$LEGACY" 2>/dev/null)" == "$CANONICAL" ]]; then pass gdrive_legacy_symlink; else fail gdrive_legacy_symlink; fi
}
check_remote(){
  if ! command -v rclone >/dev/null 2>&1; then fail gdrive_remote_api; return; fi
  # No listing output or credential details are included in receipts.
  if timeout 25s rclone lsf gdrive: --max-depth 1 --dirs-only >/dev/null 2>&1; then pass gdrive_remote_api; else fail gdrive_remote_api; fi
}
check_fuse(){
  if timeout 15s ls -U -- "$CANONICAL/backups" >/dev/null 2>&1; then pass gdrive_fuse_read; else fail gdrive_fuse_read; fi
}
check_service(){
  if systemctl --user is-active --quiet agentos-gdrive-mount.service; then pass gdrive_mount_service; else fail gdrive_mount_service; fi
  if systemctl --user is-active --quiet agentos-gdrive-health.timer; then pass gdrive_health_timer; else fail gdrive_health_timer; fi
}
check_health(){
  if [[ ! -f "$STATE" ]] || ! grep -Eq '^state=(READY|RECOVERED)$' "$STATE"; then
    fail gdrive_health_state; return
  fi
  local checked epoch now
  checked="$(sed -n 's/^checked_at=//p' "$STATE" | tail -n1)"
  epoch="$(date -d "$checked" +%s 2>/dev/null || true)"
  now="$(date +%s)"
  # Reject stale health snapshots.
  if [[ "$epoch" =~ ^[0-9]+$ ]] && (( epoch <= now && now - epoch <= 900 )); then
    pass gdrive_health_state
  else
    fail gdrive_health_state
  fi
}
check_mount
check_legacy
check_remote
check_fuse
check_service
check_health
emit disk_root_used_pct "$(df -P / 2>/dev/null | awk 'NR==2{print $5}' | tr -cd '0-9%' || true)"
emit gdrive_underlay_writer_protection UNVERIFIED
emit action_relay_log_location "$LOG"
if [[ "$failed" -eq 0 ]]; then emit oracle_gdrive_read_acceptance PASS; exit 0; else emit oracle_gdrive_read_acceptance FAIL; exit 42; fi

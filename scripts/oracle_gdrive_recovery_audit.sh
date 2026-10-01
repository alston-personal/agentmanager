#!/usr/bin/env bash
set -euo pipefail

MOUNTPOINT="${AGENTOS_GDRIVE_MOUNTPOINT:-/home/ubuntu/gdrive}"
REMOTE="${AGENTOS_GDRIVE_REMOTE:-gdrive:}"
OUT="${AGENTOS_GDRIVE_RECOVERY_DIR:-/home/ubuntu/gdrive-recovery}"

mkdir -p "$OUT"

if mountpoint -q "$MOUNTPOINT"; then
  echo "REFUSING: $MOUNTPOINT is currently mounted." >&2
  echo "This audit must inspect the local underlay before the rclone mount hides it." >&2
  exit 64
fi

echo "phase=local_underlay_scan"
du -sh "$MOUNTPOINT" 2>/dev/null || true
df -h / || true

find "$MOUNTPOINT" -type f -printf '%P\t%s\t%TY-%Tm-%TdT%TH:%TM:%TS\n' 2>/dev/null   | LC_ALL=C sort > "$OUT/local-underlay.tsv"

echo "phase=remote_scan"
rclone lsf "$REMOTE" --recursive --files-only --format 'pst'   > "$OUT/remote.tsv"

awk -F '\t' '{print $1 "\t" $2}' "$OUT/local-underlay.tsv"   | LC_ALL=C sort > "$OUT/local-path-size.tsv"

# rclone --format pst emits path;size;modtime using semicolons.
awk -F ';' 'NF >= 2 {print $1 "\t" $2}' "$OUT/remote.tsv"   | LC_ALL=C sort > "$OUT/remote-path-size.tsv"

join -t $'\t' -v 1 "$OUT/local-path-size.tsv" "$OUT/remote-path-size.tsv"   > "$OUT/local-only.tsv" || true
join -t $'\t' -v 2 "$OUT/local-path-size.tsv" "$OUT/remote-path-size.tsv"   > "$OUT/remote-only.tsv" || true
join -t $'\t' "$OUT/local-path-size.tsv" "$OUT/remote-path-size.tsv"   | awk -F '\t' '$2 != $3 {print}' > "$OUT/size-mismatch.tsv" || true

printf 'local_files=%s\n' "$(wc -l < "$OUT/local-path-size.tsv")"
printf 'remote_files=%s\n' "$(wc -l < "$OUT/remote-path-size.tsv")"
printf 'local_only=%s\n' "$(wc -l < "$OUT/local-only.tsv")"
printf 'remote_only=%s\n' "$(wc -l < "$OUT/remote-only.tsv")"
printf 'size_mismatch=%s\n' "$(wc -l < "$OUT/size-mismatch.tsv")"
echo "recovery_audit=PASS out=$OUT"

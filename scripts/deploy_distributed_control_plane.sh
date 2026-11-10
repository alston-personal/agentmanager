#!/usr/bin/env bash
# Service-specific release controller; does not switch Realm Fabric/Core pointers.
set -euo pipefail
SOURCE_REPO="${AGENTOS_REPO:-$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)}"
COMMIT="${1:?Usage: deploy_distributed_control_plane.sh FULL_COMMIT_SHA}"
[[ "$COMMIT" =~ ^[a-f0-9]{40}$ ]] || { echo 'An exact commit is required' >&2; exit 2; }
[[ "$(git -C "$SOURCE_REPO" rev-parse "$COMMIT^{commit}")" == "$COMMIT" ]]
DATA_ROOT="${AGENT_DATA_ROOT:-$HOME/agent-data}"
RELEASE="$DATA_ROOT/releases/control-plane/$COMMIT"
STATE="$DATA_ROOT/runtime/control-plane"
OVERRIDE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/agentos-control-plane.service.d"
OVERRIDE="$OVERRIDE_DIR/90-agentmanager-release.conf"
mkdir -p "$STATE" "$(dirname "$RELEASE")" "$OVERRIDE_DIR"
exec 9>"$STATE/deployment.lock"
flock -n 9 || { echo 'Control plane deployment already running' >&2; exit 3; }
if [[ ! -d "$RELEASE" ]]; then
  git -C "$SOURCE_REPO" worktree add --detach "$RELEASE" "$COMMIT"
fi
[[ "$(git -C "$RELEASE" rev-parse HEAD)" == "$COMMIT" ]]
[[ -z "$(git -C "$RELEASE" status --porcelain --untracked-files=no)" ]]
(cd "$RELEASE" && /usr/bin/python3 -m scripts.distributed_gateway --help >/dev/null)
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$STATE/$STAMP.previous-override"
HAD_OVERRIDE=0
if [[ -f "$OVERRIDE" ]]; then cp "$OVERRIDE" "$BACKUP"; HAD_OVERRIDE=1; fi
rollback() {
  if [[ "$HAD_OVERRIDE" == 1 ]]; then cp "$BACKUP" "$OVERRIDE"; else rm -f "$OVERRIDE"; fi
  systemctl --user daemon-reload
  systemctl --user restart agentos-control-plane.service
}
trap 'rollback' ERR
cat > "$OVERRIDE" <<EOF
[Service]
WorkingDirectory=$RELEASE
ExecStart=
ExecStart=/usr/bin/env PYTHONPATH=$RELEASE AGENT_PROJECT_ROOT=$RELEASE /usr/bin/python3 -m scripts.distributed_gateway
EOF
systemctl --user daemon-reload
systemctl --user restart agentos-control-plane.service
# Retry startup only; every failed receipt remains distinct from successful acceptance.
ACCEPTED=0
for ATTEMPT in 1 2 3; do
  if /usr/bin/python3 "$RELEASE/scripts/inspect_distributed_control_plane.py" --source-sha "$COMMIT" \
      --output "$STATE/$STAMP-attempt-$ATTEMPT.json"; then ACCEPTED=1; break; fi
  sleep 2
done
[[ "$ACCEPTED" == 1 ]]
trap - ERR
printf '%s\n' "$RELEASE" > "$STATE/accepted-release"
echo "Accepted control plane release: $COMMIT"

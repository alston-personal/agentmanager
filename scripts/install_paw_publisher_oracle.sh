#!/usr/bin/env bash
# Explicit opt-in ONLY: run on Oracle with root privileges after an accepted
# immutable Core deployment. Never invoked by employee wake or regular activation.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "paw_publisher_root_required" >&2; exit 2; }
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
case "$DATA_ROOT" in /*) ;; *) echo "paw_publisher_absolute_data_root_required" >&2; exit 2;; esac
RELEASE="$(readlink -f "$DATA_ROOT/runtime/core/current" 2>/dev/null || true)"
case "$RELEASE" in "$DATA_ROOT"/releases/core/*) ;; *)
  echo "paw_publisher_accepted_immutable_core_required" >&2; exit 2;;
esac
[ -d "$RELEASE" ] || { echo "paw_publisher_release_missing" >&2; exit 2; }
ENV_FILE=/etc/agentos/paw-publisher.env
[ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || {
  echo "paw_publisher_env_missing" >&2; exit 2;
}
[ "$(stat -c %u "$ENV_FILE")" -eq 0 ] && [ "$(stat -c %a "$ENV_FILE")" = 600 ] || {
  echo "paw_publisher_env_permissions_invalid" >&2; exit 2;
}
# Never source or print secret values in the installer.
grep -Eq '^(GH_TOKEN|GITHUB_TOKEN)=' "$ENV_FILE" || {
  echo "paw_publisher_credential_not_configured" >&2; exit 2;
}
src="$RELEASE/.agent/scripts"
for name in agentos-paw-publisher.service agentos-paw-publisher.timer; do
  [ -f "$src/$name" ] || { echo "paw_publisher_release_asset_missing" >&2; exit 2; }
done
# Preserve the system service boundary: this installer never invokes
# systemctl --user and never adds publishing privileges to the worker.
install -m 0644 "$src/agentos-paw-publisher.timer" /etc/systemd/system/agentos-paw-publisher.timer
sed -e "s|/home/ubuntu/agentmanager|$RELEASE|g" \
    -e "s|/home/ubuntu/agent-data|$DATA_ROOT|g" \
    "$src/agentos-paw-publisher.service" \
    > /etc/systemd/system/agentos-paw-publisher.service
chmod 0644 /etc/systemd/system/agentos-paw-publisher.service
systemctl daemon-reload
systemctl enable --now agentos-paw-publisher.timer
systemctl is-active --quiet agentos-paw-publisher.timer
printf '%s\n' 'paw_publisher_system_timer=active' 'paw_publisher_release=accepted'

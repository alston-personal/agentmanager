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
# The user service must be able to read the immutable release and its Python runtime.
[ -x "$RELEASE/.venv/bin/python3" ] || { echo "paw_publisher_release_python_missing" >&2; exit 2; }
[ -f "$RELEASE/agentos_node/paw_engineering_publisher_cli.py" ] || { echo "paw_publisher_module_missing" >&2; exit 2; }
getent passwd agentos-publisher >/dev/null || { echo 'paw_publisher_service_user_missing' >&2; exit 2; }
[ "$(id -u agentos-publisher)" != "$(id -u ubuntu)" ] || { echo 'paw_publisher_identity_not_isolated' >&2; exit 2; }
ENV_FILE=/etc/agentos/paw-publisher.env
[ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || {
  echo "paw_publisher_env_missing" >&2; exit 2;
}
[ "$(stat -c %u "$ENV_FILE")" -eq 0 ] && [ "$(stat -c %a "$ENV_FILE")" = 640 ] && [ "$(stat -c %G "$ENV_FILE")" = agentos-publisher ] || {
  echo "paw_publisher_env_permissions_invalid" >&2; exit 2;
}
# Never source or print secret values in the installer.
grep -Eq '^(GH_TOKEN|GITHUB_TOKEN)=' "$ENV_FILE" || {
  echo "paw_publisher_credential_not_configured" >&2; exit 2;
}
for target in "$RELEASE/.venv/bin/python3" "$RELEASE/agentos_node/paw_engineering_publisher_cli.py" "$DATA_ROOT/employee-runtime" "$DATA_ROOT/employee-worker-state/paw-470-worktrees"; do
  runuser -u agentos-publisher -- test -r "$target" || { echo 'paw_publisher_source_access_missing' >&2; exit 2; }
done
runuser -u agentos-publisher -- test -w "$DATA_ROOT/employee-runtime" || { echo 'paw_publisher_receipt_write_missing' >&2; exit 2; }
# Verify execute/traverse access, not just readability of a directory.
for target in "$RELEASE" "$RELEASE/.venv/bin/python3" "$DATA_ROOT" "$DATA_ROOT/employee-runtime" "$DATA_ROOT/employee-worker-state" "$DATA_ROOT/employee-worker-state/paw-470-worktrees"; do
  runuser -u agentos-publisher -- test -x "$target" || { echo "paw_publisher_traversal_access_missing" >&2; exit 2; }
done
for executable in /usr/bin/git /usr/bin/gh; do
  [ -x "$executable" ] && runuser -u agentos-publisher -- test -x "$executable" || { echo "paw_publisher_git_tools_missing" >&2; exit 2; }
done
# A read-only worktree does not imply access to its shared Git common-dir.
# Inspect every existing Paw worktree before activating an authenticated timer.
for target in "$DATA_ROOT"/employee-worker-state/paw-470-worktrees/*; do
  [ -d "$target" ] || continue
  runuser -u agentos-publisher -- git -C "$target" rev-parse --verify HEAD >/dev/null 2>&1 || { echo "paw_publisher_worktree_git_access_missing" >&2; exit 2; }
done
[ ! -L "$DATA_ROOT/employee-worker-state/paw-470-worktrees" ] || { echo "paw_publisher_worktree_symlink_invalid" >&2; exit 2; }
src="$RELEASE/.agent/scripts"
for name in agentos-paw-publisher.service agentos-paw-publisher.timer; do
  [ -f "$src/$name" ] || { echo "paw_publisher_release_asset_missing" >&2; exit 2; }
done
# Preserve the system service boundary: this installer never invokes
# systemctl --user and never adds publishing privileges to the worker.
install -m 0644 "$src/agentos-paw-publisher.timer" /etc/systemd/system/agentos-paw-publisher.timer
sed -e "s|/usr/bin/python3|$RELEASE/.venv/bin/python3|g" \
    -e "s|/home/ubuntu/agentmanager|$RELEASE|g" \
    -e "s|/home/ubuntu/agent-data|$DATA_ROOT|g" \
    "$src/agentos-paw-publisher.service" \
    > /etc/systemd/system/agentos-paw-publisher.service
chmod 0644 /etc/systemd/system/agentos-paw-publisher.service
systemctl daemon-reload
systemctl enable --now agentos-paw-publisher.timer
systemctl is-active --quiet agentos-paw-publisher.timer
printf '%s\n' 'paw_publisher_system_timer=active' 'paw_publisher_release=accepted'

#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
RUNTIME="${AGENTOS_RUNTIME_VNEXT:-$HOME/.local/share/agentos/runtime-vnext}"
SPOOL="${AGENT_DATA_ROOT:-$HOME/agent-data}/runtime/antigravity-relay"

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
git -C "$REPO" fetch origin main
git -C "$REPO" merge --ff-only origin/main

install -m 0664 "$REPO/agentos_node/antigravity_relay.py" "$RUNTIME/agentos_node/antigravity_relay.py"
install -m 0664 "$REPO/agentos_node/antigravity_relay_worker.py" "$RUNTIME/agentos_node/antigravity_relay_worker.py"

for d in "$SPOOL" "$SPOOL/inbox" "$SPOOL/processing" "$SPOOL/receipts"; do
  mkdir -p "$d"
  chgrp agentos "$d"
  chmod 2770 "$d"
done

# Do NOT restart the Antigravity service here. This script runs as a child of
# that service; restarting it here kills the worker before it can atomically
# publish the repair receipt. A separate deterministic Action Relay action does
# the restart only after this capsule has completed and its receipt is durable.
systemctl --user daemon-reload
PYTHONPATH="$RUNTIME" python3 - <<'PY'
from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.antigravity_relay_worker import AntigravityRelayWorker
print('antigravity_runtime_import=PASS')
PY

bash "$REPO/scripts/install_action_relay_user.sh"
systemctl --user is-active --quiet agentos-action-relay.service

echo "antigravity_repair=PASS"
echo "antigravity_restart_pending=YES"
echo "action_relay_install=PASS"
echo "runtime=$RUNTIME"
echo "spool=$SPOOL"

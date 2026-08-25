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

# The shared spool must remain group-owned and group-writable. Do not recursively
# chown peer artifacts: producer ownership is part of the cross-user boundary.
for d in "$SPOOL" "$SPOOL/inbox" "$SPOOL/processing" "$SPOOL/receipts"; do
  mkdir -p "$d"
  chgrp agentos "$d"
  chmod 2770 "$d"
done

# Remove the one stale incomplete receipt created by the old worker; it is not a
# valid committed receipt and otherwise blocks atomic replacement semantics.
find "$SPOOL/receipts" -maxdepth 1 -type f -name '*.json.tmp' -user ubuntu -delete

systemctl --user daemon-reload
systemctl --user restart agentos-antigravity-relay.service
sleep 1
systemctl --user is-active --quiet agentos-antigravity-relay.service
PYTHONPATH="$RUNTIME" python3 - <<'PY'
from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.antigravity_relay_worker import AntigravityRelayWorker
print('antigravity_runtime_import=PASS')
PY

echo "antigravity_repair=PASS"
echo "runtime=$RUNTIME"
echo "spool=$SPOOL"

bash "$REPO/scripts/install_action_relay_user.sh"

#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run this installer as ubuntu (not root, not agentos-node)." >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA="${AGENT_DATA_ROOT:-$HOME/agent-data}"
BRANCH="${AGENTOS_RUNTIME_BRANCH:-feature/distributed-agentos-runtime}"
RUNTIME_ROOT="${AGENTOS_RUNTIME_ROOT:-$HOME/.local/share/agentos/runtime-vnext}"
RELAY_ROOT="$DATA/runtime/antigravity-relay"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-antigravity-relay.service"

if [ ! -d "$REPO/.git" ]; then
  echo "ERROR: AgentOS repository not found at $REPO" >&2
  exit 2
fi

# The relay protocol depends on both OS identities being members of the same
# dedicated group. Directory ownership alone is insufficient because capsules
# and receipts are created by different users.
if ! id -Gn ubuntu | tr ' ' '\n' | grep -qx agentos; then
  echo "ERROR: ubuntu is not a member of the required shared group: agentos" >&2
  echo "Run: sudo usermod -aG agentos ubuntu" >&2
  echo "Then start a fresh login/session (or reboot) before rerunning this installer." >&2
  exit 3
fi
if ! id -Gn agentos-node | tr ' ' '\n' | grep -qx agentos; then
  echo "ERROR: agentos-node is not a member of the required shared group: agentos" >&2
  echo "Run: sudo usermod -aG agentos agentos-node" >&2
  echo "Then restart the runner service/session before rerunning this installer." >&2
  exit 3
fi

mkdir -p "$(dirname "$RUNTIME_ROOT")" "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts" "$UNIT_DIR"
chgrp agentos "$RELAY_ROOT" "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts"
chmod 2770 "$RELAY_ROOT" "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts"

# Normalize existing spool artifacts where ubuntu owns them. Old producer-owned
# files are left alone; the next producer/worker revision will enforce group
# assignment explicitly for all new artifacts.
find "$RELAY_ROOT/receipts" -maxdepth 1 -type f -user ubuntu -name 'relay-*.json*' -exec chgrp agentos {} + 2>/dev/null || true
find "$RELAY_ROOT/receipts" -maxdepth 1 -type f -user ubuntu -name 'relay-*.json*' -exec chmod 660 {} + 2>/dev/null || true

# The human workspace may intentionally remain on main and may be dirty. Never
# switch/reset it just to run the relay. Keep a dedicated detached worktree that
# tracks the canonical vNext branch instead.
git -C "$REPO" fetch origin "$BRANCH"
if [ -e "$RUNTIME_ROOT/.git" ]; then
  git -C "$RUNTIME_ROOT" reset --hard "origin/$BRANCH"
else
  if [ -e "$RUNTIME_ROOT" ]; then
    if [ -n "$(find "$RUNTIME_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
      echo "ERROR: runtime root exists and is not an AgentOS worktree: $RUNTIME_ROOT" >&2
      exit 2
    fi
    rmdir "$RUNTIME_ROOT" 2>/dev/null || true
  fi
  git -C "$REPO" worktree add --detach "$RUNTIME_ROOT" "origin/$BRANCH"
fi

(
  cd "$RUNTIME_ROOT"
  PYTHONPATH="$RUNTIME_ROOT" /usr/bin/python3 - <<'PY'
from agentos_node.antigravity_relay_worker import discover_executor
print("runtime_import=ok")
print("executor=", discover_executor())
PY
)

cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Antigravity Relay (ubuntu session boundary)
After=default.target

[Service]
Type=simple
WorkingDirectory=$RUNTIME_ROOT
Environment=PYTHONPATH=$RUNTIME_ROOT
UMask=0007
ExecStart=/usr/bin/python3 -m agentos_node.antigravity_relay_worker --root $RELAY_ROOT
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-antigravity-relay.service
systemctl --user restart agentos-antigravity-relay.service
sleep 1
systemctl --user --no-pager --full status agentos-antigravity-relay.service || true

echo
echo "ubuntu_groups=$(id -Gn ubuntu)"
echo "agentos_node_groups=$(id -Gn agentos-node)"
echo "runtime_root=$RUNTIME_ROOT"
echo "runtime_branch=$BRANCH"
echo "relay_root=$RELAY_ROOT"
echo "relay_mode=$(stat -c '%a %U %G' "$RELAY_ROOT")"
echo "inbox_mode=$(stat -c '%a %U %G' "$RELAY_ROOT/inbox")"
echo "installed=$UNIT"

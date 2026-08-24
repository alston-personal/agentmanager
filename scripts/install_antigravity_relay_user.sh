#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run this installer as ubuntu (not root, not agentos-node)." >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA="${AGENT_DATA_ROOT:-$HOME/agent-data}"
RELAY_ROOT="$DATA/runtime/antigravity-relay"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-antigravity-relay.service"

mkdir -p "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts" "$UNIT_DIR"

cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Antigravity Relay (ubuntu session boundary)
After=default.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
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
sleep 1
systemctl --user --no-pager --full status agentos-antigravity-relay.service || true

echo
python3 - <<'PY'
from agentos_node.antigravity_relay_worker import discover_executor
print("executor=", discover_executor())
PY

echo "relay_root=$RELAY_ROOT"
echo "installed=$UNIT"

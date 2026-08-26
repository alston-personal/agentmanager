#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
RUNTIME="${AGENTOS_RUNTIME_VNEXT:-$HOME/.local/share/agentos/runtime-vnext}"
REALM_RUNTIME="$HOME/.local/share/agentos/realm-fabric/current"
DATA_ROOT="${AGENT_DATA_ROOT:-$HOME/agent-data}"
SPOOL="$DATA_ROOT/runtime/antigravity-relay"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-antigravity-relay.service"
REALM_UNIT="$UNIT_DIR/agentos-realm-fabric.service"

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$RUNTIME/agentos_node" "$REALM_RUNTIME/agent_core" "$UNIT_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Runtime repair must not depend on the mutable checkout being clean or fast-forwardable.
# Fetch canonical main, then materialize only trusted runtime inputs from the fetched
# Git object. This preserves local checkout state and provides a deterministic repair.
git -C "$REPO" fetch origin main
git -C "$REPO" show origin/main:agentos_node/__init__.py > "$TMPDIR/__init__.py"
git -C "$REPO" show origin/main:agentos_node/antigravity_relay.py > "$TMPDIR/antigravity_relay.py"
git -C "$REPO" show origin/main:agentos_node/antigravity_relay_worker.py > "$TMPDIR/antigravity_relay_worker.py"
git -C "$REPO" show origin/main:scripts/install_action_relay_user.sh > "$TMPDIR/install_action_relay_user.sh"

# Realm Fabric is intentionally tiny and stdlib-only. Materialize only its four
# canonical modules rather than merging or cleaning the live checkout.
git -C "$REPO" show origin/main:agent_core/__init__.py > "$TMPDIR/agent_core_init.py"
git -C "$REPO" show origin/main:agent_core/node_registry.py > "$TMPDIR/node_registry.py"
git -C "$REPO" show origin/main:agent_core/realm_fabric.py > "$TMPDIR/realm_fabric.py"
git -C "$REPO" show origin/main:agent_core/realm_server.py > "$TMPDIR/realm_server.py"
git -C "$REPO" show origin/main:agent_core/realm_cli.py > "$TMPDIR/realm_cli.py"

install -m 0664 "$TMPDIR/__init__.py" "$RUNTIME/agentos_node/__init__.py"
install -m 0664 "$TMPDIR/antigravity_relay.py" "$RUNTIME/agentos_node/antigravity_relay.py"
install -m 0664 "$TMPDIR/antigravity_relay_worker.py" "$RUNTIME/agentos_node/antigravity_relay_worker.py"
install -m 0664 "$TMPDIR/agent_core_init.py" "$REALM_RUNTIME/agent_core/__init__.py"
install -m 0664 "$TMPDIR/node_registry.py" "$REALM_RUNTIME/agent_core/node_registry.py"
install -m 0664 "$TMPDIR/realm_fabric.py" "$REALM_RUNTIME/agent_core/realm_fabric.py"
install -m 0664 "$TMPDIR/realm_server.py" "$REALM_RUNTIME/agent_core/realm_server.py"
install -m 0664 "$TMPDIR/realm_cli.py" "$REALM_RUNTIME/agent_core/realm_cli.py"

for d in "$SPOOL" "$SPOOL/inbox" "$SPOOL/processing" "$SPOOL/receipts"; do
  mkdir -p "$d"
  chgrp agentos "$d"
  chmod 2770 "$d"
done

# The ubuntu user manager was started before the agentos supplementary-group
# grant, so its children may not inherit agentos even though /etc/group is
# correct. Pin the boundary explicitly with `sg agentos` on every relay start.
cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Antigravity Relay (ubuntu identity, agentos boundary)
After=default.target

[Service]
Type=simple
WorkingDirectory=$RUNTIME
Environment=PYTHONPATH=$RUNTIME
UMask=0007
ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker --root $SPOOL'
Restart=on-failure
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

# Install ONE Realm Fabric as a separate localhost-only Core service. It has no
# public route here; first-node bootstrap will use an SSH tunnel until HTTPS/QR
# enrollment is promoted in a later version.
AGENT_DATA_ROOT="$DATA_ROOT" PYTHONPATH="$REALM_RUNTIME" /usr/bin/python3 -m agent_core.realm_cli init --realm-id realm-alston >/dev/null
cat > "$REALM_UNIT" <<EOF
[Unit]
Description=AgentOS ONE Realm Fabric (ubuntu Core identity)
After=network.target

[Service]
Type=simple
WorkingDirectory=$REALM_RUNTIME
Environment=PYTHONPATH=$REALM_RUNTIME
Environment=AGENT_DATA_ROOT=$DATA_ROOT
UMask=0007
ExecStart=/usr/bin/python3 -m agent_core.realm_cli serve --host 127.0.0.1 --port 8780
Restart=always
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

# Do NOT restart Antigravity from inside its own request. Reload the unit only;
# Action Relay performs that restart after repair side effects are observed.
systemctl --user daemon-reload
systemctl --user enable --now agentos-realm-fabric.service
(
  cd "$RUNTIME"
  PYTHONPATH="$RUNTIME" python3 - <<'PY'
from agentos_node.antigravity_relay import AntigravityRelayClient
from agentos_node.antigravity_relay_worker import AntigravityRelayWorker
print('antigravity_runtime_import=PASS')
PY
)

AGENTOS_REPO="$REPO" bash "$TMPDIR/install_action_relay_user.sh"
systemctl --user is-active --quiet agentos-action-relay.service
systemctl --user is-active --quiet agentos-realm-fabric.service
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8780/v1/health >/dev/null; then break; fi
  sleep 1
done
REALM_HEALTH=$(curl -fsS --max-time 3 http://127.0.0.1:8780/v1/health)
echo "realm_fabric_health=$REALM_HEALTH"

echo "antigravity_repair=PASS"
echo "antigravity_source=origin/main"
echo "antigravity_checkout_merge=SKIPPED"
echo "antigravity_group_context=agentos"
echo "antigravity_restart_pending=YES"
echo "action_relay_install=PASS"
echo "realm_fabric_install=PASS"
echo "realm_fabric_port=8780"
echo "realm_fabric_public_route=NONE"
echo "runtime=$RUNTIME"
echo "realm_runtime=$REALM_RUNTIME"
echo "spool=$SPOOL"
echo "unit=$UNIT"
echo "realm_unit=$REALM_UNIT"

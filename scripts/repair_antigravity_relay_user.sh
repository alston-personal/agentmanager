#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

# realm_fabric_deploy_authority_separation_v1
# This transport repair owns only Antigravity Relay + Action Relay. Realm Fabric
# is governed by the generation-fenced deployment primitive and MUST NOT be
# materialized, have its unit rewritten, or be restarted from this script.
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
RUNTIME="${AGENTOS_RUNTIME_VNEXT:-/home/ubuntu/.local/share/agentos/runtime-vnext}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
SPOOL="$DATA_ROOT/runtime/antigravity-relay"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-antigravity-relay.service"
REALM_UNIT="$UNIT_DIR/agentos-realm-fabric.service"

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$RUNTIME/agentos_node" "$UNIT_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Runtime repair must not depend on the mutable checkout being clean or
# fast-forwardable. Materialize only the relay dependency closure from fetched
# canonical main. Realm Fabric is intentionally excluded by authority design.
git -C "$REPO" fetch origin main
git -C "$REPO" show origin/main:agentos_node/__init__.py > "$TMPDIR/__init__.py"
git -C "$REPO" show origin/main:agentos_node/antigravity_relay.py > "$TMPDIR/antigravity_relay.py"
git -C "$REPO" show origin/main:agentos_node/antigravity_relay_worker.py > "$TMPDIR/antigravity_relay_worker.py"
git -C "$REPO" show origin/main:scripts/install_action_relay_user.sh > "$TMPDIR/install_action_relay_user.sh"

install -m 0664 "$TMPDIR/__init__.py" "$RUNTIME/agentos_node/__init__.py"
install -m 0664 "$TMPDIR/antigravity_relay.py" "$RUNTIME/agentos_node/antigravity_relay.py"
install -m 0664 "$TMPDIR/antigravity_relay_worker.py" "$RUNTIME/agentos_node/antigravity_relay_worker.py"

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

# Do NOT restart Antigravity from inside its own request. Action Relay performs
# that restart after repair side effects are observed.
systemctl --user daemon-reload
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

# Realm Fabric checks are read-only. Failing health is surfaced, but this repair
# has no authority to mutate or restart Realm Fabric.
systemctl --user is-active --quiet agentos-realm-fabric.service
REALM_HEALTH=$(curl -fsS --max-time 3 http://127.0.0.1:8780/v1/health)
echo "realm_fabric_health=$REALM_HEALTH"

echo "antigravity_repair=PASS"
echo "antigravity_source=origin/main"
echo "antigravity_checkout_merge=SKIPPED"
echo "antigravity_group_context=agentos"
echo "antigravity_restart_pending=YES"
echo "action_relay_install=PASS"
echo "realm_fabric_install=SKIPPED_FENCED_AUTHORITY"
echo "realm_fabric_mutation=NONE"
echo "realm_fabric_deploy_authority_separation=PASS"
echo "runtime=$RUNTIME"
echo "spool=$SPOOL"
echo "unit=$UNIT"
echo "realm_unit=$REALM_UNIT"

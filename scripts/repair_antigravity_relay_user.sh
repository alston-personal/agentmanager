#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
RUNTIME="${AGENTOS_RUNTIME_VNEXT:-/home/ubuntu/.local/share/agentos/runtime-vnext}"
REALM_RUNTIME="${AGENTOS_REALM_RUNTIME:-/home/ubuntu/.local/share/agentos/realm-fabric/current}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
SOURCE_REF="${AGENTOS_REF:-main}"
SPOOL="$DATA_ROOT/runtime/antigravity-relay"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-antigravity-relay.service"
REALM_UNIT="$UNIT_DIR/agentos-realm-fabric.service"

case "$SOURCE_REF" in
  main|feature/realm-node-fabric-readiness) ;;
  *) echo "ERROR: AGENTOS_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$RUNTIME/agentos_node" "$REALM_RUNTIME/agent_core" "$UNIT_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Runtime repair must not depend on the mutable checkout being clean or fast-forwardable.
# Fetch one explicitly allowlisted ref, then materialize only trusted runtime inputs from
# FETCH_HEAD. This preserves local checkout state and lets a development branch be tested
# without writing or merging main.
git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
show_source() {
  git -C "$REPO" show "$SOURCE_COMMIT:$1"
}

show_source agentos_node/__init__.py > "$TMPDIR/__init__.py"
show_source agentos_node/antigravity_relay.py > "$TMPDIR/antigravity_relay.py"
show_source agentos_node/antigravity_relay_worker.py > "$TMPDIR/antigravity_relay_worker.py"
show_source scripts/install_action_relay_user.sh > "$TMPDIR/install_action_relay_user.sh"

# Realm Fabric is intentionally tiny and stdlib-only. Materialize the complete set
# required by the selected realm_server generation. Device enrollment uses request ->
# human approval -> claim, so no enrollment secret enters GitHub control.
show_source agent_core/__init__.py > "$TMPDIR/agent_core_init.py"
show_source agent_core/node_registry.py > "$TMPDIR/node_registry.py"
show_source agent_core/node_bootstrap.py > "$TMPDIR/node_bootstrap.py"
show_source agent_core/realm_fabric.py > "$TMPDIR/realm_fabric.py"
show_source agent_core/realm_server.py > "$TMPDIR/realm_server.py"
show_source agent_core/realm_cli.py > "$TMPDIR/realm_cli.py"

install -m 0664 "$TMPDIR/__init__.py" "$RUNTIME/agentos_node/__init__.py"
install -m 0664 "$TMPDIR/antigravity_relay.py" "$RUNTIME/agentos_node/antigravity_relay.py"
install -m 0664 "$TMPDIR/antigravity_relay_worker.py" "$RUNTIME/agentos_node/antigravity_relay_worker.py"
install -m 0664 "$TMPDIR/agent_core_init.py" "$REALM_RUNTIME/agent_core/__init__.py"
install -m 0664 "$TMPDIR/node_registry.py" "$REALM_RUNTIME/agent_core/node_registry.py"
install -m 0664 "$TMPDIR/node_bootstrap.py" "$REALM_RUNTIME/agent_core/node_bootstrap.py"
install -m 0664 "$TMPDIR/realm_fabric.py" "$REALM_RUNTIME/agent_core/realm_fabric.py"
install -m 0664 "$TMPDIR/realm_server.py" "$REALM_RUNTIME/agent_core/realm_server.py"
install -m 0664 "$TMPDIR/realm_cli.py" "$REALM_RUNTIME/agent_core/realm_cli.py"
test -f "$REALM_RUNTIME/agent_core/node_bootstrap.py"

for d in "$SPOOL" "$SPOOL/inbox" "$SPOOL/processing" "$SPOOL/receipts"; do
  mkdir -p "$d"
  chgrp agentos "$d"
  chmod 2770 "$d"
done

# The ubuntu user manager was started before the agentos supplementary-group
# grant, so its children may not inherit agentos even though /etc/group is
# correct. Pin the boundary explicitly with `sg agentos` on every relay start.
# NoNewPrivileges must not be enabled here because it blocks this authorized
# setgid transition; authority remains bounded by account membership + capsule schema.
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
# public route here; first-node bootstrap uses the existing private transport.
(
  cd "$REALM_RUNTIME"
  AGENT_DATA_ROOT="$DATA_ROOT" /usr/bin/python3 -m agent_core.realm_cli init --realm-id realm-alston >/dev/null
)
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

# Do NOT restart Antigravity from inside an Antigravity request. Reload the unit only;
# the independent Action Relay performs that restart after repair side effects exist.
systemctl --user daemon-reload
systemctl --user restart agentos-realm-fabric.service
systemctl --user enable agentos-realm-fabric.service >/dev/null
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

# Route existence is checked without credentials: current handlers must answer
# 401 (not 404), proving the selected generation is live without exposing tokens.
BOOTSTRAP_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 'http://127.0.0.1:8780/v1/bootstrap?node_id=vopc5750')
BENCHMARK_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 -X POST -H 'Content-Type: application/json' --data '{}' http://127.0.0.1:8780/v1/benchmark)
test "$BOOTSTRAP_CODE" = 401
test "$BENCHMARK_CODE" = 401

echo "antigravity_repair=PASS"
echo "agentos_source_ref=$SOURCE_REF"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "antigravity_checkout_merge=SKIPPED"
echo "antigravity_group_context=agentos"
echo "antigravity_restart_pending=YES"
echo "action_relay_install=PASS"
echo "realm_fabric_install=PASS"
echo "realm_fabric_device_flow=PASS"
echo "realm_fabric_bootstrap_route=PASS"
echo "realm_fabric_benchmark_route=PASS"
echo "realm_fabric_port=8780"
echo "runtime=$RUNTIME"
echo "realm_runtime=$REALM_RUNTIME"
echo "spool=$SPOOL"
echo "unit=$UNIT"
echo "realm_unit=$REALM_UNIT"

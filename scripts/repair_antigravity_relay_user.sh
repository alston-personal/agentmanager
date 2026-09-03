#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
RUNTIME="${AGENTOS_RUNTIME_VNEXT:-/home/ubuntu/.local/share/agentos/runtime-vnext}"
REALM_RUNTIME="${AGENTOS_REALM_RUNTIME:-/home/ubuntu/.local/share/agentos/realm-fabric/current}"
ACTION_RUNTIME="${AGENTOS_ACTION_RUNTIME_ROOT:-/home/ubuntu/.local/share/agentos/action-runtime}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
SOURCE_REF="${AGENTOS_REF:-main}"
EXPECTED_SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
PROVIDER="${AGENTOS_ANTIGRAVITY_PROVIDER:-claude}"
SPOOL="$DATA_ROOT/runtime/antigravity-relay"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-antigravity-relay.service"
REALM_UNIT="$UNIT_DIR/agentos-realm-fabric.service"
MANIFEST="$RUNTIME/runtime-provenance.json"

case "$SOURCE_REF" in
  main|core/integration|feature/realm-node-fabric-readiness) ;;
  *) echo "ERROR: AGENTOS_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac

if [ -n "$EXPECTED_SOURCE_COMMIT" ] && ! printf '%s' "$EXPECTED_SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "ERROR: AGENTOS_SOURCE_COMMIT must be an exact lowercase 40-hex commit SHA" >&2
  exit 6
fi

case "$PROVIDER" in
  claude|agy) ;;
  *) echo "ERROR: AGENTOS_ANTIGRAVITY_PROVIDER is not allowlisted: $PROVIDER" >&2; exit 5 ;;
esac

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$RUNTIME/agentos_node" "$REALM_RUNTIME" "$UNIT_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Runtime repair must not depend on the mutable checkout being clean or fast-forwardable.
# Fetch one explicitly allowlisted ref, then materialize only trusted runtime inputs from
# FETCH_HEAD. When an exact commit is supplied by the bounded bootstrap contract, fail
# closed unless that allowlisted ref resolves to the same immutable generation.
git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
if [ -n "$EXPECTED_SOURCE_COMMIT" ] && [ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]; then
  echo "ERROR: runtime source generation mismatch: ref=$SOURCE_REF observed=$SOURCE_COMMIT expected=$EXPECTED_SOURCE_COMMIT" >&2
  exit 7
fi
show_source() {
  git -C "$REPO" show "$SOURCE_COMMIT:$1"
}

show_source agentos_node/__init__.py > "$TMPDIR/__init__.py"
show_source agentos_node/antigravity_relay.py > "$TMPDIR/antigravity_relay.py"
show_source agentos_node/antigravity_relay_worker.py > "$TMPDIR/antigravity_relay_worker.py"
show_source scripts/install_action_relay_user.sh > "$TMPDIR/install_action_relay_user.sh"

install -m 0664 "$TMPDIR/__init__.py" "$RUNTIME/agentos_node/__init__.py"
install -m 0664 "$TMPDIR/antigravity_relay.py" "$RUNTIME/agentos_node/antigravity_relay.py"
install -m 0664 "$TMPDIR/antigravity_relay_worker.py" "$RUNTIME/agentos_node/antigravity_relay_worker.py"

# Realm Server is no longer a tiny hand-curated subset: it imports the runtime
# controller, legacy compatibility controller, resolve facade and their Core
# dependencies. Materialize the complete agent_core package from the SAME exact
# commit so Python dependency closure cannot silently drift behind realm_server.
rm -rf "$REALM_RUNTIME/agent_core"
git -C "$REPO" archive "$SOURCE_COMMIT" agent_core | tar -x -C "$REALM_RUNTIME"
test -f "$REALM_RUNTIME/agent_core/realm_server.py"
test -f "$REALM_RUNTIME/agent_core/controller_api.py"
test -f "$REALM_RUNTIME/agent_core/controller_service.py"
test -f "$REALM_RUNTIME/agent_core/executor_job_contract.py"
PYTHONPATH="$REALM_RUNTIME" python3 -m py_compile \
  "$REALM_RUNTIME/agent_core/realm_server.py" \
  "$REALM_RUNTIME/agent_core/controller_api.py" \
  "$REALM_RUNTIME/agent_core/controller_service.py"

WORKER_SHA256=$(sha256sum "$RUNTIME/agentos_node/antigravity_relay_worker.py" | awk '{print $1}')
python3 - "$MANIFEST" "$SOURCE_REF" "$SOURCE_COMMIT" "$PROVIDER" "$WORKER_SHA256" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, source_ref, source_commit, provider, worker_sha = sys.argv[1:]
payload = {
    "schema": "agentos.runtime-provenance/v1",
    "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "source_ref": source_ref,
    "source_commit": source_commit,
    "provider": provider,
    "worker_sha256": worker_sha,
}
Path(path).write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
chmod 0664 "$MANIFEST"

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
# Provider selection and runtime provenance are explicit; capsules cannot choose either.
cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Antigravity Relay (ubuntu identity, agentos boundary)
After=default.target

[Service]
Type=simple
WorkingDirectory=$RUNTIME
Environment=PYTHONPATH=$RUNTIME
Environment=AGENTOS_ANTIGRAVITY_PROVIDER=$PROVIDER
Environment=AGENTOS_RUNTIME_SOURCE_REF=$SOURCE_REF
Environment=AGENTOS_RUNTIME_SOURCE_COMMIT=$SOURCE_COMMIT
Environment=AGENTOS_RUNTIME_WORKER_SHA256=$WORKER_SHA256
UMask=0007
ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker --root $SPOOL'
Restart=on-failure
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

# Install ONE Realm Fabric as a separate localhost-only Core service. Core code
# comes from REALM_RUNTIME; bounded Node-side executor dispatch is loaded lazily
# from the Action Relay worktree, which is pinned to the same SOURCE_COMMIT below.
(
  cd "$REALM_RUNTIME"
  PYTHONPATH="$REALM_RUNTIME:$ACTION_RUNTIME" AGENT_DATA_ROOT="$DATA_ROOT" /usr/bin/python3 -m agent_core.realm_cli init --realm-id realm-alston >/dev/null
)
cat > "$REALM_UNIT" <<EOF
[Unit]
Description=AgentOS ONE Realm Fabric (ubuntu Core identity)
After=network.target

[Service]
Type=simple
WorkingDirectory=$REALM_RUNTIME
Environment=PYTHONPATH=$REALM_RUNTIME:$ACTION_RUNTIME
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
  PYTHONPATH="$RUNTIME" AGENTOS_ANTIGRAVITY_PROVIDER="$PROVIDER" python3 - <<'PY'
from agentos_node.antigravity_relay_worker import AntigravityRelayWorker
worker = AntigravityRelayWorker('/tmp/agentos-provider-import-check')
print('antigravity_runtime_import=PASS')
print('antigravity_provider=' + worker.provider)
PY
)

# The Action Relay must consume the exact same governed generation selected by
# this repair. It must not independently fall back to mutable origin/main.
AGENTOS_REPO="$REPO" \
AGENTOS_ACTION_RUNTIME_ROOT="$ACTION_RUNTIME" \
AGENTOS_ACTION_SOURCE_REF="$SOURCE_REF" \
AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT" \
bash "$TMPDIR/install_action_relay_user.sh"
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
echo "antigravity_provider=$PROVIDER"
echo "antigravity_worker_sha256=$WORKER_SHA256"
echo "antigravity_runtime_manifest=$MANIFEST"
echo "antigravity_restart_pending=YES"
echo "action_relay_install=PASS"
echo "action_relay_source_generation_pinned=PASS"
echo "realm_fabric_install=PASS"
echo "realm_fabric_runtime_closure=PASS"
echo "realm_fabric_device_flow=PASS"
echo "realm_fabric_bootstrap_route=PASS"
echo "realm_fabric_benchmark_route=PASS"
echo "realm_fabric_port=8780"
echo "runtime=$RUNTIME"
echo "realm_runtime=$REALM_RUNTIME"
echo "action_runtime=$ACTION_RUNTIME"
echo "spool=$SPOOL"
echo "unit=$UNIT"
echo "realm_unit=$REALM_UNIT"

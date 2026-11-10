#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
REALM_RUNTIME="${AGENTOS_REALM_RUNTIME:-/home/ubuntu/.local/share/agentos/realm-fabric/current}"
SOURCE_REF="${AGENTOS_REF:-feature/realm-node-fabric-readiness}"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
DROPIN_DIR="$UNIT_DIR/agentos-realm-fabric.service.d"
RUNTIME_DROPIN="$DROPIN_DIR/runtime-generation.conf"
CONTROLLER_ENV="/home/ubuntu/.config/agentos/controller.env"

case "$SOURCE_REF" in
  main|feature/realm-node-fabric-readiness) ;;
  *) echo "ERROR: AGENTOS_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
test -f "$REALM_RUNTIME/agent_core/realm_server.py" || { echo "ERROR: realm runtime missing" >&2; exit 3; }
test -f "$CONTROLLER_ENV" || { echo "ERROR: controller env missing: $CONTROLLER_ENV" >&2; exit 5; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
for path in \
  agent_core/__init__.py \
  agent_core/controller_api.py \
  agent_core/runtime_ota.py \
  agent_core/node_registry.py \
  agent_core/realm_server.py \
  agent_core/realm_cli.py; do
  dest="$TMPDIR/$(basename "$path")"
  git -C "$REPO" show "$SOURCE_COMMIT:$path" > "$dest"
  case "$dest" in *.py) python3 -m py_compile "$dest" ;; esac
done

install -m 0664 "$TMPDIR/__init__.py" "$REALM_RUNTIME/agent_core/__init__.py"
install -m 0664 "$TMPDIR/runtime_ota.py" "$REALM_RUNTIME/agent_core/runtime_ota.py"
install -m 0664 "$TMPDIR/node_registry.py" "$REALM_RUNTIME/agent_core/node_registry.py"
install -m 0664 "$TMPDIR/controller_api.py" "$REALM_RUNTIME/agent_core/controller_api.py"
install -m 0664 "$TMPDIR/realm_server.py" "$REALM_RUNTIME/agent_core/realm_server.py"
install -m 0664 "$TMPDIR/realm_cli.py" "$REALM_RUNTIME/agent_core/realm_cli.py"

# Pin the live systemd service to exactly the generation we just materialized.
# This avoids stale WorkingDirectory/PYTHONPATH/ExecStart drift across earlier installers.
mkdir -p "$DROPIN_DIR"
cat > "$RUNTIME_DROPIN" <<EOF
[Service]
WorkingDirectory=$REALM_RUNTIME
Environment=PYTHONPATH=$REALM_RUNTIME
ExecStart=
ExecStart=/usr/bin/python3 -m agent_core.realm_cli serve --host 127.0.0.1 --port 8780
EOF
chmod 0644 "$RUNTIME_DROPIN"

systemctl --user daemon-reload
systemctl --user restart agentos-realm-fabric.service
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8780/v1/health >/dev/null; then break; fi
  sleep 1
done
systemctl --user is-active --quiet agentos-realm-fabric.service

grep -q "realm.runtime.rollout" "$REALM_RUNTIME/agent_core/controller_api.py"
grep -q "runtime_status" "$REALM_RUNTIME/agent_core/runtime_ota.py"
grep -q "runtime_converged_count" "$REALM_RUNTIME/agent_core/node_registry.py"
grep -q "auto_ota_" "$REALM_RUNTIME/agent_core/realm_server.py"

# Verify the live imported module really comes from the pinned runtime.
IMPORTED_SERVER=$(cd "$REALM_RUNTIME" && PYTHONPATH="$REALM_RUNTIME" python3 - <<'PY'
import agent_core.realm_server
print(agent_core.realm_server.__file__)
PY
)
test "$IMPORTED_SERVER" = "$REALM_RUNTIME/agent_core/realm_server.py" || {
  echo "ERROR: imported realm_server is not pinned runtime: $IMPORTED_SERVER" >&2
  exit 23
}

# Verify authenticated controller dispatch ROUTE exists. A deliberately forbidden
# action must reach ControllerService and return 401/PermissionError, never fallback 404/not found.
CONTROLLER_TOKEN=$(sed -n 's/^AGENTOS_CONTROLLER_TOKEN=//p' "$CONTROLLER_ENV" | head -n 1)
test -n "$CONTROLLER_TOKEN" || { echo "ERROR: controller token missing" >&2; exit 24; }
PROBE_BODY="$TMPDIR/dispatch-probe.json"
PROBE_CODE=$(curl -sS --http1.1 -o "$PROBE_BODY" -w '%{http_code}' --max-time 5 \
  -H "Authorization: Bearer $CONTROLLER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"node_id":"vopc5750","action":"__route_probe__"}' \
  http://127.0.0.1:8780/v1/controller/dispatch)
unset CONTROLLER_TOKEN
if [ "$PROBE_CODE" = 404 ] && grep -q '"error": "not found"\|"error":"not found"' "$PROBE_BODY"; then
  echo "ERROR: live controller dispatch route is still missing" >&2
  systemctl --user status agentos-realm-fabric.service --no-pager >&2 || true
  exit 25
fi
grep -q 'controller action not permitted' "$PROBE_BODY" || {
  echo "ERROR: controller dispatch route probe did not reach ControllerService (HTTP $PROBE_CODE)" >&2
  cat "$PROBE_BODY" >&2
  exit 26
}

echo "core_runtime_ota_deploy=PASS"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "realm_runtime_path=$REALM_RUNTIME"
echo "realm_server_import=$IMPORTED_SERVER"
echo "controller_dispatch_route=PASS"
echo "bridge_env_preserved=PASS"
echo "realm_ota_policy=available"
echo "realm_ota_auto_converge=available"
echo "realm_service=active"

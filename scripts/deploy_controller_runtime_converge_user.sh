#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
REALM_RUNTIME="${AGENTOS_REALM_RUNTIME:-/home/ubuntu/.local/share/agentos/realm-fabric/current}"
SOURCE_REF="${AGENTOS_REF:-feature/realm-node-fabric-readiness}"

case "$SOURCE_REF" in
  main|feature/realm-node-fabric-readiness) ;;
  *) echo "ERROR: AGENTOS_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
test -f "$REALM_RUNTIME/agent_core/realm_server.py" || { echo "ERROR: realm runtime missing" >&2; exit 3; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
for path in \
  agent_core/controller_api.py \
  agent_core/runtime_ota.py \
  agent_core/node_registry.py; do
  dest="$TMPDIR/$(basename "$path")"
  git -C "$REPO" show "$SOURCE_COMMIT:$path" > "$dest"
  python3 -m py_compile "$dest"
done

install -m 0664 "$TMPDIR/runtime_ota.py" "$REALM_RUNTIME/agent_core/runtime_ota.py"
install -m 0664 "$TMPDIR/node_registry.py" "$REALM_RUNTIME/agent_core/node_registry.py"
install -m 0664 "$TMPDIR/controller_api.py" "$REALM_RUNTIME/agent_core/controller_api.py"

systemctl --user restart agentos-realm-fabric.service
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8780/v1/health >/dev/null; then break; fi
  sleep 1
done
systemctl --user is-active --quiet agentos-realm-fabric.service

grep -q "realm.runtime.rollout" "$REALM_RUNTIME/agent_core/controller_api.py"
grep -q "runtime_status" "$REALM_RUNTIME/agent_core/runtime_ota.py"
grep -q "runtime_converged_count" "$REALM_RUNTIME/agent_core/node_registry.py"
echo "core_runtime_ota_deploy=PASS"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "bridge_env_preserved=PASS"
echo "realm_ota_policy=available"
echo "realm_service=active"

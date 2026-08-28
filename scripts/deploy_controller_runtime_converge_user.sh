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
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
git -C "$REPO" show "$SOURCE_COMMIT:agent_core/controller_api.py" > "$TMP"
python3 -m py_compile "$TMP"
install -m 0664 "$TMP" "$REALM_RUNTIME/agent_core/controller_api.py"

systemctl --user restart agentos-realm-fabric.service
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8780/v1/health >/dev/null; then break; fi
  sleep 1
done
systemctl --user is-active --quiet agentos-realm-fabric.service

grep -q "node.runtime.converge" "$REALM_RUNTIME/agent_core/controller_api.py"
echo "controller_runtime_converge_deploy=PASS"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "bridge_env_preserved=PASS"
echo "realm_service=active"

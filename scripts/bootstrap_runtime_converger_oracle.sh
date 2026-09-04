#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: bootstrap must run as ubuntu" >&2
  exit 2
fi

SOURCE_REF="${1:-}"
SOURCE_COMMIT="${2:-}"
REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA="${AGENT_DATA_ROOT:-$HOME/agent-data}"
MARKER="$DATA/runtime/action-relay/capabilities.json"

if [ "$SOURCE_REF" != "core/integration" ]; then
  echo "ERROR: bootstrap source_ref must be core/integration" >&2
  exit 4
fi
if ! printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "ERROR: bootstrap source_commit must be a lowercase 40-character git SHA" >&2
  exit 4
fi

test -d "$REPO/.git" || { echo "ERROR: canonical repo missing" >&2; exit 2; }
cd "$REPO"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "ERROR: refusing bootstrap with tracked local changes" >&2
  exit 2
fi
CURRENT="$(git rev-parse HEAD)"
if [ "$CURRENT" != "$SOURCE_COMMIT" ]; then
  echo "ERROR: canonical checkout must already be detached at requested exact SHA" >&2
  exit 4
fi

git fetch --no-tags origin "$SOURCE_REF"
FETCHED="$(git rev-parse FETCH_HEAD)"
if [ "$FETCHED" != "$SOURCE_COMMIT" ]; then
  echo "ERROR: requested SHA is not the current permitted source-ref head" >&2
  exit 4
fi

# The bootstrap carrier is explicit/manual only. The installer receives an exact
# immutable generation and cannot choose another ref or silently drift.
AGENTOS_ACTION_SOURCE_REF="$SOURCE_REF" \
AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT" \
bash scripts/install_action_relay_user.sh

python3 - "$MARKER" "$SOURCE_COMMIT" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2]
payload = json.loads(path.read_text(encoding="utf-8"))
assert payload.get("schema") == "agentos.action-relay-capabilities/v1"
assert payload.get("source_ref") == "core/integration"
assert payload.get("source_commit") == expected
assert set(payload.get("actions") or []) == {"agentos.executor.job", "agentos.runtime.converge"}
assert payload.get("node_capabilities") == ["node.runtime.converge"]
PY

# Restart ONE from the same exact checkout so its Core manifest projects the
# installed marker. This does not grant steady-state authority to this script.
bash scripts/install_realm_fabric_user.sh
systemctl --user is-active --quiet agentos-action-relay.service
systemctl --user is-active --quiet agentos-realm-fabric.service
curl -fsS --max-time 5 http://127.0.0.1:8780/v1/health >/dev/null

# Local source-level proof that the manifest sees the installed marker.
AGENT_DATA_ROOT="$DATA" python3 - <<'PY'
from agent_core.realm_server import _core_node_manifest
manifest = _core_node_manifest("bootstrap-proof")
assert "node.runtime.converge" in set(manifest.get("capabilities") or [])
PY

# Operating proof: the restarted Realm process must have persisted its own Core
# manifest + heartbeat into the durable Node Registry. Source presence alone is
# not acceptance. Retry briefly only for process-start scheduling; never mutate
# the registry from this bootstrap proof.
registered=0
for _ in $(seq 1 10); do
  if AGENT_DATA_ROOT="$DATA" python3 - <<'PY'
from agent_core.node_registry import NodeRegistry

node_map = NodeRegistry().node_map()
matches = [n for n in node_map.get("nodes", []) if n.get("node_id") == "oracle-core-node"]
assert len(matches) == 1
node = matches[0]
assert node.get("status") == "online"
assert "node.runtime.converge" in set(node.get("capabilities") or [])
assert node.get("heartbeat_age_seconds") is not None
assert node.get("heartbeat_age_seconds") <= node.get("heartbeat_stale_after_seconds", 30)
PY
  then
    registered=1
    break
  fi
  sleep 1
done
if [ "$registered" -ne 1 ]; then
  rm -f "$MARKER"
  echo "ERROR: restarted Realm did not self-register oracle-core-node with live bounded converge capability" >&2
  exit 4
fi

echo "runtime_converger_bootstrap=PASS"
echo "runtime_converger_source_ref=$SOURCE_REF"
echo "runtime_converger_source_commit=$SOURCE_COMMIT"
echo "runtime_converger_capability=node.runtime.converge"
echo "runtime_converger_core_node_registration=PASS"

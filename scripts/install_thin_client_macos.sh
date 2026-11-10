#!/bin/bash
set -euo pipefail

REF="${1:-core/integration}"
ONE_URL="${AGENTOS_ONE_URL:-https://studio.milkcat.org/dashboard/api/agentos}"
NODE_ID="${AGENTOS_NODE_ID:-mbpr}"
ROOT="$HOME/Library/Application Support/AgentOS"
VENV="$ROOT/venv"
STATE="$HOME/.agentos"
WORKSPACE="$HOME/AgentOS"
LAUNCHER="$ROOT/agentos-client"

command -v python3 >/dev/null || { echo "python3 is required"; exit 2; }
command -v git >/dev/null || { echo "git is required"; exit 2; }

mkdir -p "$ROOT" "$STATE" "$WORKSPACE"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade "git+https://github.com/alston-personal/agentmanager.git@$REF"

cat > "$LAUNCHER" <<EOF
#!/bin/bash
export AGENTOS_CLIENT_HOME="$STATE"
exec "$VENV/bin/agentos-client" "\$@"
EOF
chmod 700 "$LAUNCHER"

if [ ! -f "$STATE/policy.json" ]; then
  "$LAUNCHER" policy-init --root "$WORKSPACE"
fi

if [ ! -f "$STATE/client.json" ]; then
  echo "agentos_macos_install=ENROLLMENT_REQUIRED"
  echo "agentos_node_id=$NODE_ID"
  exec "$LAUNCHER" join --one "$ONE_URL" --node-id "$NODE_ID" --timeout-seconds 900
fi

"$VENV/bin/python" - <<'PY'
from agentos_node.onboarding import install_macos_node_supervisor
import json
r=install_macos_node_supervisor()
print(json.dumps(r, ensure_ascii=False))
if not r.get("supervisor_ready"):
    raise SystemExit(2)
PY
"$LAUNCHER" health
"$LAUNCHER" once
echo "agentos_macos_install=PASS"
echo "agentos_node_id=$NODE_ID"

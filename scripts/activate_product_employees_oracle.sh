#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT/.env"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WAKE_UNIT_SRC="$ROOT/.agent/scripts/agentos-employee-wake-node.service"
WAKE_UNIT_DST="$USER_SYSTEMD_DIR/agentos-employee-wake-node.service"
WAKE_NODE_ID="oracle-employee-wake-node"

[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
[ -f "$HOME/.agentos.secrets" ] && source "$HOME/.agentos.secrets"
set +a

[ "${AGENT_MODE:-CLIENT}" = "CORE" ] || { echo "Product Employee activation requires AGENT_MODE=CORE" >&2; exit 2; }
DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
case "$DATA_ROOT" in /*) ;; *) echo "AGENT_DATA_ROOT must be absolute" >&2; exit 2;; esac
[ -f "$DATA_ROOT/realm/fabric.json" ] || { echo "Missing existing Realm fabric" >&2; exit 2; }
[ -f "$DATA_ROOT/realm/nodes.json" ] || { echo "Missing existing Node registry" >&2; exit 2; }
[ -f "$WAKE_UNIT_SRC" ] || { echo "Missing wake node service asset" >&2; exit 2; }

RUNTIME_ROOT="$DATA_ROOT/employee-runtime"
WAKE_ROOT="$DATA_ROOT/employee-wakes"
WAKE_NODE_ROOT="$DATA_ROOT/employee-wake-node"
WAKE_CONFIG="$WAKE_NODE_ROOT/client.json"
HOST_STATE_ROOT="$DATA_ROOT/employee-worker-host"
WORKER_STATE_ROOT="$DATA_ROOT/employee-worker-state"
mkdir -p "$RUNTIME_ROOT" "$WAKE_ROOT" "$WAKE_NODE_ROOT" "$HOST_STATE_ROOT" "$WORKER_STATE_ROOT" "$USER_SYSTEMD_DIR"
chmod 700 "$WAKE_NODE_ROOT"

PYTHON_BIN="$ROOT/.venv/bin/python3"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

PYTHONPATH="$ROOT" "$PYTHON_BIN" "$ROOT/scripts/bootstrap_product_employees.py" --runtime-root "$RUNTIME_ROOT"
PYTHONPATH="$ROOT" "$PYTHON_BIN" -m agentos_node.employee_wake_node \
  --data-root "$DATA_ROOT" \
  --config "$WAKE_CONFIG" \
  --wake-root "$WAKE_ROOT" \
  --runtime-root "$RUNTIME_ROOT" \
  bootstrap
[ -f "$WAKE_CONFIG" ] || { echo "Wake node config was not created" >&2; exit 2; }
chmod 600 "$WAKE_CONFIG"

# Install Supervisor one_direct and the existing shared Worker Host through their
# canonical installer. These flags are fixed by this activation profile and do
# not provide executable/argv/product authority.
AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1 \
AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE=1 \
AGENTOS_EMPLOYEE_WAKE_ROOT="$WAKE_ROOT" \
AGENTOS_EMPLOYEE_WORKER_NODE_ID="$WAKE_NODE_ID" \
AGENTOS_EMPLOYEE_WORKER_HOST_STATE_ROOT="$HOST_STATE_ROOT" \
AGENTOS_EMPLOYEE_WORKER_STATE_ROOT="$WORKER_STATE_ROOT" \
  bash "$ROOT/scripts/install_systemd_user.sh"

# Render the fixed wake-only Node unit for this checkout/data root. No token is
# embedded in the unit or EnvironmentFile; the daemon reads the 0600 ClientConfig.
"$PYTHON_BIN" - "$WAKE_UNIT_SRC" "$WAKE_UNIT_DST" "$ROOT" "$DATA_ROOT" "$PYTHON_BIN" <<'PY'
from pathlib import Path
import sys
src, dst, root, data_root, python_bin = sys.argv[1:]
text = Path(src).read_text(encoding="utf-8")
text = text.replace("/home/ubuntu/agentmanager", root)
text = text.replace("/home/ubuntu/agent-data", data_root)
text = text.replace("/usr/bin/python3", python_bin)
Path(dst).write_text(text, encoding="utf-8")
PY

systemctl --user daemon-reload
systemctl --user enable agentos-employee-wake-node.service >/dev/null
systemctl --user restart agentos-employee-wake-node.service
systemctl --user is-active --quiet agentos-employee-wake-node.service
systemctl --user is-active --quiet agentos-core-supervisor.service
systemctl --user is-active --quiet agentos-employee-worker-host.service

# The wake Node must become eligible before acceptance. Presence and work claims
# are created by the daemon/Supervisor; this bootstrap does not synthesize them.
ready=0
for _ in $(seq 1 10); do
  if PYTHONPATH="$ROOT" "$PYTHON_BIN" - "$DATA_ROOT/realm/nodes.json" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
d=json.loads(p.read_text())
nodes=d.get('nodes') or {}
node=nodes.get('oracle-employee-wake-node') if isinstance(nodes, dict) else None
raise SystemExit(0 if isinstance(node,dict) and node.get('status') == 'online' and node.get('capabilities') == ['agent.employee.wake.deliver'] else 1)
PY
  then
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" -eq 1 ] || { echo "Wake node did not advertise exact bounded capability" >&2; exit 4; }

echo "product_employee_activation=PASS"
echo "wake_node_id=$WAKE_NODE_ID"
echo "wake_capability=agent.employee.wake.deliver"
echo "supervisor_delivery=one_direct"
echo "worker_host=active"
echo "verified_marker_emitted=false"

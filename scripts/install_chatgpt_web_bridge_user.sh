#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "chatgpt_web_bridge_install=WRONG_USER" >&2
  exit 2
fi
: "${AGENTOS_SOURCE_COMMIT:?AGENTOS_SOURCE_COMMIT required}"

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
ROOT="$HOME/.local/share/agentos/chatgpt-web/bridge"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VENV="$HOME/.local/share/agentos/gui-worker/venv"
mkdir -p "$ROOT/requests" "$ROOT/receipts" "$UNIT_DIR"
chmod 700 "$ROOT" "$ROOT/requests" "$ROOT/receipts"
test -x "$VENV/bin/python"

# Both web-surface installers rewrite shared AgentOS modules in the canonical
# checkout. Serialize that mutation across providers so concurrent workflow
# runs cannot steal or remove each other's temporary files.
command -v flock >/dev/null 2>&1 || { echo "web_bridge_runtime_lock=FLOCK_MISSING" >&2; exit 3; }
exec 8>/tmp/agentos-web-bridge-runtime.lock
flock -w 240 8 || { echo "web_bridge_runtime_lock=TIMEOUT" >&2; exit 7; }
echo "web_bridge_runtime_lock=PASS"

for rel in agentos_node/chatgpt_web_bridge.py agentos_node/session_bridge.py agentos_node/agent_surfaces.py agentos_node/bootstrap_control.py agentos_node/bootstrap_scheduler.py; do
  git -C "$REPO" show "$AGENTOS_SOURCE_COMMIT:$rel" > "$REPO/$rel.tmp"
  mv "$REPO/$rel.tmp" "$REPO/$rel"
done
python3 -m py_compile   "$REPO/agentos_node/chatgpt_web_bridge.py"   "$REPO/agentos_node/session_bridge.py"   "$REPO/agentos_node/agent_surfaces.py"   "$REPO/agentos_node/bootstrap_control.py"   "$REPO/agentos_node/bootstrap_scheduler.py"

cat > "$UNIT_DIR/agentos-chatgpt-web-bridge.service" <<EOF
[Unit]
Description=AgentOS ChatGPT Web Surface Bridge
After=agentos-gui-browser.service
Requires=agentos-gui-browser.service

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
Environment=AGENTOS_CHATGPT_WEB_BRIDGE=$ROOT
Environment=AGENTOS_GUI_CDP_URL=http://127.0.0.1:9222
ExecStart=$VENV/bin/python -m agentos_node.chatgpt_web_bridge --serve
Restart=always
RestartSec=2
MemoryHigh=768M
MemoryMax=1536M
CPUQuota=100%

[Install]
WantedBy=default.target
EOF

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user daemon-reload
systemctl --user enable --now agentos-chatgpt-web-bridge.service >/dev/null
systemctl --user restart agentos-bootstrap-gui.service
systemctl --user is-active --quiet agentos-chatgpt-web-bridge.service
systemctl --user is-active --quiet agentos-bootstrap-gui.service

for _ in $(seq 1 30); do
  if [ -s "$ROOT/bridge.json" ] && [ -s "$ROOT/sessions.json" ]; then break; fi
  sleep 1
done
test -s "$ROOT/bridge.json"
test -s "$ROOT/sessions.json"

python3 - "$ROOT/bridge.json" "$ROOT/sessions.json" <<'PY'
import json,sys
b=json.load(open(sys.argv[1],encoding='utf-8'))
s=json.load(open(sys.argv[2],encoding='utf-8'))
assert b.get('schema')=='agentos.session-bridge/v0.1',b
assert b.get('provider')=='chatgpt-web',b
assert b.get('ready') is True,b
assert s.get('schema')=='agentos.session-index/v0.1',s
assert s.get('provider')=='chatgpt-web',s
print('chatgpt_web_bridge_provider=chatgpt-web')
print('chatgpt_web_bridge_sessions='+str(len(s.get('sessions') or [])))
PY
echo "chatgpt_web_bridge_install=PASS"

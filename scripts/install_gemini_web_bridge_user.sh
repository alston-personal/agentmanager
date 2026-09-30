#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_bridge_install=WRONG_USER" >&2
  exit 2
fi
: "${AGENTOS_SOURCE_COMMIT:?AGENTOS_SOURCE_COMMIT required}"

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
ROOT="$HOME/.local/share/agentos/gemini-web/bridge"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VENV="$HOME/.local/share/agentos/gui-worker/venv"
mkdir -p "$ROOT/requests" "$ROOT/receipts" "$UNIT_DIR"
chmod 700 "$ROOT" "$ROOT/requests" "$ROOT/receipts"
test -x "$VENV/bin/python"

for rel in \
  agentos_node/web_agent_surface.py \
  agentos_node/gemini_web_bridge.py \
  agentos_node/session_bridge.py \
  agentos_node/agent_surfaces.py \
  agentos_node/bootstrap_control.py \
  agentos_node/bootstrap_scheduler.py; do
  git -C "$REPO" show "$AGENTOS_SOURCE_COMMIT:$rel" > "$REPO/$rel.tmp"
  mv "$REPO/$rel.tmp" "$REPO/$rel"
done

python3 -m py_compile \
  "$REPO/agentos_node/web_agent_surface.py" \
  "$REPO/agentos_node/gemini_web_bridge.py" \
  "$REPO/agentos_node/session_bridge.py" \
  "$REPO/agentos_node/agent_surfaces.py" \
  "$REPO/agentos_node/bootstrap_control.py" \
  "$REPO/agentos_node/bootstrap_scheduler.py"

cat > "$UNIT_DIR/agentos-gemini-web-bridge.service" <<EOF
[Unit]
Description=AgentOS Gemini Web Surface Bridge
After=agentos-gui-browser.service
Requires=agentos-gui-browser.service

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
Environment=AGENTOS_GEMINI_WEB_BRIDGE=$ROOT
Environment=AGENTOS_GUI_CDP_URL=http://127.0.0.1:9222
ExecStart=$VENV/bin/python -m agentos_node.gemini_web_bridge --serve
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
systemctl --user enable --now agentos-gemini-web-bridge.service >/dev/null
systemctl --user restart agentos-bootstrap-gui.service
systemctl --user is-active --quiet agentos-gemini-web-bridge.service
systemctl --user is-active --quiet agentos-bootstrap-gui.service

for _ in $(seq 1 30); do
  [ -s "$ROOT/bridge.json" ] && break
  sleep 1
done
test -s "$ROOT/bridge.json"

python3 - "$ROOT/bridge.json" <<'PY'
import json,sys
b=json.load(open(sys.argv[1],encoding='utf-8'))
assert b.get('schema')=='agentos.session-bridge/v0.1',b
assert b.get('provider')=='gemini-web',b
assert b.get('ready') is True,b
print('gemini_web_bridge_provider=gemini-web')
print('gemini_web_bridge_service=PASS')
PY
echo "gemini_web_bridge_install=PASS"

# acceptance retrigger: gemini-web-mvp

# readiness recheck 2026-09-30T08:57Z

# final READY acceptance after interactive login 2026-09-30T08:59Z

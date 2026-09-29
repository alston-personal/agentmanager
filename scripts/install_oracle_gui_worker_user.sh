#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "agentos_gui_worker_install=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
BIN="$ROOT/bin"
PROFILE="$ROOT/chromium-profile"
LOG="$ROOT/logs"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DISPLAY_NUM=":99"
SCREEN="1440x900x24"

mkdir -p "$BIN" "$PROFILE" "$LOG" "$UNIT_DIR"
chmod 700 "$ROOT" "$PROFILE"

if ! sudo -n true >/dev/null 2>&1; then
  echo "agentos_gui_worker_install=SUDO_UNAVAILABLE" >&2
  exit 3
fi

APT_SOURCES="$ROOT/ubuntu.sources.list"
. /etc/os-release
CODENAME="${VERSION_CODENAME:-jammy}"
cat > "$APT_SOURCES" <<EOF
deb http://ports.ubuntu.com/ubuntu-ports $CODENAME main universe multiverse restricted
deb http://ports.ubuntu.com/ubuntu-ports $CODENAME-updates main universe multiverse restricted
deb http://ports.ubuntu.com/ubuntu-ports $CODENAME-security main universe multiverse restricted
EOF
sudo -n apt-get -o Dir::Etc::sourcelist="$APT_SOURCES" -o Dir::Etc::sourceparts="-" update -y >/dev/null
sudo -n DEBIAN_FRONTEND=noninteractive apt-get \
  -o Dir::Etc::sourcelist="$APT_SOURCES" -o Dir::Etc::sourceparts="-" \
  install -y xvfb openbox x11vnc novnc websockify dbus-x11 python3-venv python3-pip fonts-noto-cjk >/dev/null

VENV="$ROOT/venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip wheel >/dev/null
"$VENV/bin/python" -m pip install --upgrade playwright >/dev/null
"$VENV/bin/python" -m playwright install chromium >/dev/null

BROWSER="$("$VENV/bin/python" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
PY
)"
test -x "$BROWSER"
printf '%s\n' "$BROWSER" > "$ROOT/browser-path"
chmod 600 "$ROOT/browser-path"

cat > "$BIN/start-browser.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$HOME/.local/share/agentos/gui-worker"
BROWSER="$(cat "$ROOT/browser-path")"
exec "$BROWSER" \
  --user-data-dir="$ROOT/chromium-profile" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  about:blank
EOF
chmod 700 "$BIN/start-browser.sh"

cat > "$UNIT_DIR/agentos-gui-display.service" <<EOF
[Unit]
Description=AgentOS GUI Worker virtual display

[Service]
Type=simple
Environment=DISPLAY=$DISPLAY_NUM
ExecStart=/usr/bin/Xvfb $DISPLAY_NUM -screen 0 $SCREEN -nolisten tcp -ac
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/agentos-gui-window-manager.service" <<EOF
[Unit]
Description=AgentOS GUI Worker window manager
After=agentos-gui-display.service
Requires=agentos-gui-display.service

[Service]
Type=simple
Environment=DISPLAY=$DISPLAY_NUM
ExecStart=/usr/bin/openbox-session
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/agentos-gui-browser.service" <<EOF
[Unit]
Description=AgentOS GUI Worker persistent Chromium
After=agentos-gui-display.service agentos-gui-window-manager.service
Requires=agentos-gui-display.service

[Service]
Type=simple
Environment=DISPLAY=$DISPLAY_NUM
Environment=XDG_RUNTIME_DIR=/run/user/1001
ExecStart=$BIN/start-browser.sh
Restart=always
RestartSec=3
# Browser work is expendable; it must never be able to consume the whole VM.
MemoryHigh=25%
MemoryMax=35%
TasksMax=512
CPUQuota=200%
OOMPolicy=stop

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/agentos-gui-vnc.service" <<EOF
[Unit]
Description=AgentOS GUI Worker localhost VNC
After=agentos-gui-display.service
Requires=agentos-gui-display.service

[Service]
Type=simple
Environment=DISPLAY=$DISPLAY_NUM
ExecStart=/usr/bin/x11vnc -display $DISPLAY_NUM -localhost -rfbport 5901 -forever -shared -nopw -quiet
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/agentos-gui-novnc.service" <<EOF
[Unit]
Description=AgentOS GUI Worker localhost noVNC
After=agentos-gui-vnc.service
Requires=agentos-gui-vnc.service

[Service]
Type=simple
ExecStart=/usr/bin/websockify --web=/usr/share/novnc/ 127.0.0.1:6080 127.0.0.1:5901
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now \
  agentos-gui-display.service \
  agentos-gui-window-manager.service \
  agentos-gui-browser.service \
  agentos-gui-vnc.service \
  agentos-gui-novnc.service >/dev/null

for unit in agentos-gui-display agentos-gui-window-manager agentos-gui-browser agentos-gui-vnc agentos-gui-novnc; do
  systemctl --user is-active --quiet "$unit.service" || {
    systemctl --user --no-pager --full status "$unit.service" >&2 || true
    exit 4
  }
done

python3 - <<'PY'
import json, time, urllib.request
for _ in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=2) as r:
            d=json.load(r)
        assert d.get('webSocketDebuggerUrl')
        print('agentos_gui_worker_cdp=PASS')
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit('CDP readiness failed')
PY

python3 - <<'PY'
import socket
for port,name in [(5901,'vnc'),(6080,'novnc')]:
    s=socket.create_connection(('127.0.0.1',port),timeout=2)
    s.close()
    print(f'agentos_gui_worker_{name}=PASS')
PY

cat > "$ROOT/capability.json" <<EOF
{
  "schema": "agentos.gui-worker/v1",
  "node_role": "gui-worker",
  "capabilities": [
    "browser.gui",
    "browser.cdp",
    "browser.persistent_profile",
    "desktop.remote_view"
  ],
  "display": "$DISPLAY_NUM",
  "cdp_url": "http://127.0.0.1:9222",
  "novnc_url": "http://127.0.0.1:6080/vnc.html",
  "network_exposure": "localhost_only"
}
EOF
chmod 600 "$ROOT/capability.json"

echo "agentos_gui_worker_install=PASS"
echo "agentos_gui_worker_display=$DISPLAY_NUM"
echo "agentos_gui_worker_cdp_url=http://127.0.0.1:9222"
echo "agentos_gui_worker_novnc_url=http://127.0.0.1:6080/vnc.html"
echo "agentos_gui_worker_exposure=localhost_only"

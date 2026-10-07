#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "browser_identity_sessions_install=WRONG_USER" >&2
  exit 2
fi

SOURCE_COMMIT="${1:-${AGENTOS_SOURCE_COMMIT:-}}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

GUI_ROOT="$HOME/.local/share/agentos/gui-worker"
BROWSER_PATH="$GUI_ROOT/browser-path"
test -s "$BROWSER_PATH"
BROWSER="$(cat "$BROWSER_PATH")"
test -x "$BROWSER"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"

install_session() {
  local session="$1" port="$2" root="$3" unit="$4"
  local profile="$root/chromium-profile"
  local bin="$root/bin"
  mkdir -p "$profile" "$bin"
  chmod 700 "$root" "$profile" "$bin"

  cat > "$bin/start-browser.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$BROWSER" \
  --user-data-dir="$profile" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=$port \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  about:blank
EOF
  chmod 700 "$bin/start-browser.sh"

  cat > "$UNIT_DIR/$unit.service" <<EOF
[Unit]
Description=AgentOS persistent browser identity session $session
After=agentos-gui-display.service agentos-gui-window-manager.service
Requires=agentos-gui-display.service

[Service]
Type=simple
Environment=DISPLAY=:99
Environment=XDG_RUNTIME_DIR=/run/user/1001
ExecStart=$bin/start-browser.sh
Restart=always
RestartSec=3
MemoryHigh=infinity
MemoryMax=3G
MemoryOOMGroup=yes
TasksMax=256
CPUQuota=150%
OOMPolicy=stop
RuntimeMaxSec=12h
TimeoutStopSec=20s
KillMode=control-group

[Install]
WantedBy=default.target
EOF

  cat > "$root/session.json" <<EOF
{
  "schema": "agentos.browser-identity-session/v1",
  "session": "$session",
  "source_commit": "$SOURCE_COMMIT",
  "profile_dir": "$profile",
  "cdp_url": "http://127.0.0.1:$port",
  "shared_display": ":99"
}
EOF
  chmod 600 "$root/session.json"
}

# Preserve the already-established Oursong profile location for compatibility.
install_session "threads:oursong" 9223 "$GUI_ROOT/threads/oursong" "agentos-threads-browser-oursong"
install_session "threads:mio" 9224 "$GUI_ROOT/threads/mio" "agentos-threads-browser-mio"
install_session "google:flow" 9225 "$GUI_ROOT/providers/google-flow" "agentos-google-flow-browser"

REGISTRY="$GUI_ROOT/browser-sessions.json"
cat > "$REGISTRY" <<EOF
{
  "schema": "agentos.browser-session-registry/v1",
  "sessions": {
    "general": {"cdp_url": "http://127.0.0.1:9222"},
    "threads:oursong": {"cdp_url": "http://127.0.0.1:9223"},
    "threads:mio": {"cdp_url": "http://127.0.0.1:9224"},
    "google:flow": {"cdp_url": "http://127.0.0.1:9225"},
    "diagnostic": {"cdp_url": "http://127.0.0.1:9299"}
  }
}
EOF
chmod 600 "$REGISTRY"

systemctl --user daemon-reload
for unit in agentos-threads-browser-oursong agentos-threads-browser-mio agentos-google-flow-browser; do
  systemctl --user enable --now "$unit.service" >/dev/null
  systemctl --user restart "$unit.service"
done

python3 - <<'PY'
import json,time,urllib.request
sessions={"threads:oursong":9223,"threads:mio":9224,"google:flow":9225}
for name,port in sessions.items():
    ok=False
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",timeout=2) as r:
                d=json.load(r)
            if d.get("webSocketDebuggerUrl"):
                ok=True
                break
        except Exception:
            time.sleep(1)
    if not ok:
        raise SystemExit(f"{name} CDP readiness failed")
    print("browser_identity_session="+name)
    print("browser_identity_session_cdp=PASS")
PY

echo "browser_identity_sessions_install=PASS"
echo "browser_identity_sessions_registry=$REGISTRY"

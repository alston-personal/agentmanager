#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "oursong_threads_session_install=WRONG_USER" >&2
  exit 2
fi

SOURCE_COMMIT="${1:-${AGENTOS_SOURCE_COMMIT:-}}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

GUI_ROOT="$HOME/.local/share/agentos/gui-worker"
BROWSER_PATH="$GUI_ROOT/browser-path"
test -s "$BROWSER_PATH"
BROWSER="$(cat "$BROWSER_PATH")"
test -x "$BROWSER"

ROOT="$GUI_ROOT/threads/oursong"
PROFILE="$ROOT/chromium-profile"
BIN="$ROOT/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$PROFILE" "$BIN" "$UNIT_DIR"
chmod 700 "$ROOT" "$PROFILE" "$BIN"

cat > "$BIN/start-browser.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$BROWSER" \
  --user-data-dir="$PROFILE" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9223 \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  about:blank
EOF
chmod 700 "$BIN/start-browser.sh"

cat > "$UNIT_DIR/agentos-threads-browser-oursong.service" <<EOF
[Unit]
Description=AgentOS Threads persistent Chromium for Oursong
After=agentos-gui-display.service agentos-gui-window-manager.service
Requires=agentos-gui-display.service

[Service]
Type=simple
Environment=DISPLAY=:99
Environment=XDG_RUNTIME_DIR=/run/user/1001
ExecStart=$BIN/start-browser.sh
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

systemctl --user daemon-reload
systemctl --user enable --now agentos-threads-browser-oursong.service >/dev/null
systemctl --user restart agentos-threads-browser-oursong.service
systemctl --user is-active --quiet agentos-threads-browser-oursong.service

python3 - <<'PY'
import json,time,urllib.request
for _ in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:9223/json/version',timeout=2) as r:
            d=json.load(r)
        assert d.get('webSocketDebuggerUrl')
        print('oursong_threads_session_cdp=PASS')
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit('Oursong CDP readiness failed')
PY

cat > "$ROOT/provenance.json" <<EOF
{
  "schema": "agentos.threads-persona-session/v1",
  "persona_id": "oursong",
  "account": "oursong_alstonhuang",
  "source_commit": "$SOURCE_COMMIT",
  "profile_dir": "$PROFILE",
  "cdp_url": "http://127.0.0.1:9223",
  "shared_display": ":99"
}
EOF
chmod 600 "$ROOT/provenance.json"

echo "oursong_threads_session_install=PASS"
echo "oursong_threads_session_profile=$PROFILE"
echo "oursong_threads_session_cdp_url=http://127.0.0.1:9223"
echo "oursong_threads_session_mio_isolated=true"

#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_start=WRONG_USER" >&2
  exit 2
fi

ROOT="/home/ubuntu/agent-data/runtime/social/threads-web-dm"
PROFILE="$ROOT/browser-profile"
SESSION="$ROOT/login-session"
mkdir -p "$PROFILE" "$SESSION"
chmod 700 "$ROOT" "$PROFILE" "$SESSION"

# Fixed, bounded dependencies only. Do not run a global apt-get update here:
# unrelated third-party repositories must not break the disposable Threads login capability.
missing=()
for pkg in xvfb x11vnc novnc websockify; do
  dpkg-query -W -f='\${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed' || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "threads_web_dm_login_missing_packages=${missing[*]}"
  sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null
fi

BIN="$HOME/.local/bin"
mkdir -p "$BIN"
CLOUDFLARED="$BIN/cloudflared"
if [ ! -x "$CLOUDFLARED" ]; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    aarch64|arm64) ASSET="cloudflared-linux-arm64" ;;
    x86_64|amd64) ASSET="cloudflared-linux-amd64" ;;
    *) echo "threads_web_dm_login_start=UNSUPPORTED_ARCH"; exit 3 ;;
  esac
  TMP="$(mktemp)"
  curl -fsSL --max-time 90 "https://github.com/cloudflare/cloudflared/releases/latest/download/$ASSET" -o "$TMP"
  install -m 0755 "$TMP" "$CLOUDFLARED"
  rm -f "$TMP"
fi

# Stop an older disposable login session if present.
if [ -f "$SESSION/pids" ]; then
  tac "$SESSION/pids" | while read -r pid; do
    case "$pid" in ''|*[!0-9]*) continue ;; esac
    kill "$pid" 2>/dev/null || true
  done
fi
rm -f "$SESSION/pids" "$SESSION/"*.log "$SESSION/url.txt" "$SESSION/vnc-pass.txt"

VNC_PASS="$(python3 - <<'PY'
import secrets,string
alphabet=string.ascii_letters+string.digits
print(''.join(secrets.choice(alphabet) for _ in range(12)))
PY
)"
x11vnc -storepasswd "$VNC_PASS" "$SESSION/passwd" >/dev/null
chmod 600 "$SESSION/passwd"
printf '%s\n' "$VNC_PASS" > "$SESSION/vnc-pass.txt"
chmod 600 "$SESSION/vnc-pass.txt"

Xvfb :97 -screen 0 1280x900x24 -nolisten tcp >"$SESSION/xvfb.log" 2>&1 &
XPID=$!
echo "$XPID" >> "$SESSION/pids"

# Bootstrap authentication in a normal headed Chromium process. Playwright is
# intentionally not attached during the human login step; the existing DM bridge
# reuses this same persistent profile after authentication.
CHROME=""
for candidate in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$candidate" >/dev/null 2>&1; then
    CHROME="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$CHROME" ]; then
  CHROME="$(python3 - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
PY
)"
fi
if [ ! -x "$CHROME" ]; then
  echo "threads_web_dm_login_start=BROWSER_UNAVAILABLE"
  exit 5
fi
DISPLAY=:97 "$CHROME" \
  --user-data-dir="$PROFILE" \
  --window-size=1280,900 \
  --no-first-run \
  --no-default-browser-check \
  "https://www.threads.com/messages" >"$SESSION/browser.log" 2>&1 &
BPID=$!
echo "$BPID" >> "$SESSION/pids"

x11vnc -display :97 -rfbauth "$SESSION/passwd" -localhost -forever -shared -quiet >"$SESSION/x11vnc.log" 2>&1 &
VPID=$!
echo "$VPID" >> "$SESSION/pids"

websockify --web /usr/share/novnc 127.0.0.1:6080 127.0.0.1:5900 >"$SESSION/websockify.log" 2>&1 &
WPID=$!
echo "$WPID" >> "$SESSION/pids"

"$CLOUDFLARED" tunnel --no-autoupdate --url http://127.0.0.1:6080 >"$SESSION/cloudflared.log" 2>&1 &
CPID=$!
echo "$CPID" >> "$SESSION/pids"

URL=""
for _ in $(seq 1 60); do
  URL="$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' "$SESSION/cloudflared.log" | head -n1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "threads_web_dm_login_start=TUNNEL_FAILED"
  exit 4
fi

LOGIN_URL="$URL/vnc.html?autoconnect=1&resize=scale&path=websockify"
printf '%s\n' "$LOGIN_URL" > "$SESSION/url.txt"
chmod 600 "$SESSION/url.txt"

# Best-effort TTL cleanup after 30 minutes.
if command -v systemd-run >/dev/null 2>&1; then
  systemd-run --user --quiet --unit=agentos-threads-web-dm-login-expire --on-active=30m     /bin/sh -lc 'if [ -f /home/ubuntu/agent-data/runtime/social/threads-web-dm/login-session/pids ]; then tac /home/ubuntu/agent-data/runtime/social/threads-web-dm/login-session/pids | while read p; do kill "$p" 2>/dev/null || true; done; fi' || true
fi

echo "threads_web_dm_login_start=PASS"
echo "threads_web_dm_login_url=$LOGIN_URL"
echo "threads_web_dm_login_password=$VNC_PASS"
echo "threads_web_dm_login_ttl_minutes=30"

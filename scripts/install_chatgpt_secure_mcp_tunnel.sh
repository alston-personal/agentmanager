#!/usr/bin/env bash
set -euo pipefail

VERSION="v0.0.13"
INSTALL_ROOT="${AGENTOS_OPENAI_TUNNEL_INSTALL_ROOT:-$HOME/.local/lib/agentos/tunnel-client/$VERSION}"
CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/agentos"
ENV_FILE="${AGENTOS_OPENAI_TUNNEL_ENV_FILE:-$CONFIG_ROOT/openai-tunnel.env}"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
MCP_URL="${AGENTOS_CHATGPT_MCP_URL:-http://127.0.0.1:8000/mcp}"

case "$(uname -m)" in
  x86_64|amd64)
    PLATFORM="linux-amd64"
    EXPECTED_SHA256="e71f37b424126513173d5e3590687c0b5ccf6e8ef3fba900104d1f8c60dad906"
    ;;
  aarch64|arm64)
    PLATFORM="linux-arm64"
    EXPECTED_SHA256="9d214a805bec213a3a156dc2a4460a6dfe2f35b0c00ba20609d002bf5e6469f8"
    ;;
  *)
    echo "Unsupported tunnel-client architecture: $(uname -m)" >&2
    exit 2
    ;;
esac

TUNNEL_ID="${CONTROL_PLANE_TUNNEL_ID:-${OPENAI_MCP_TUNNEL_ID:-}}"
RUNTIME_KEY="${CONTROL_PLANE_API_KEY:-${OPENAI_MCP_TUNNEL_API_KEY:-}}"
[ -n "$TUNNEL_ID" ] || { echo "blocked_missing_openai_tunnel_id" >&2; exit 3; }
[ -n "$RUNTIME_KEY" ] || { echo "blocked_missing_openai_tunnel_runtime_key" >&2; exit 3; }
case "$TUNNEL_ID" in
  tunnel_[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "Invalid CONTROL_PLANE_TUNNEL_ID format" >&2; exit 3 ;;
esac

mkdir -p "$INSTALL_ROOT" "$CONFIG_ROOT" "$USER_SYSTEMD_DIR"
chmod 700 "$CONFIG_ROOT"

ARCHIVE="tunnel-client-${VERSION}-${PLATFORM}.zip"
URL="https://github.com/openai/tunnel-client/releases/download/${VERSION}/${ARCHIVE}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
curl -fsSL "$URL" -o "$TMP_DIR/$ARCHIVE"
printf '%s  %s\n' "$EXPECTED_SHA256" "$TMP_DIR/$ARCHIVE" | sha256sum -c - >/dev/null

python3 - "$TMP_DIR/$ARCHIVE" "$INSTALL_ROOT" <<'PY'
from pathlib import Path
import stat, sys, zipfile
archive=Path(sys.argv[1]); target=Path(sys.argv[2])
with zipfile.ZipFile(archive) as zf:
    for info in zf.infolist():
        name=Path(info.filename)
        if name.is_absolute() or ".." in name.parts:
            raise SystemExit(f"unsafe archive member: {info.filename}")
    zf.extractall(target)
executables=[]
for path in target.rglob("tunnel-client"):
    if path.is_file():
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        executables.append(path)
if len(executables) != 1:
    raise SystemExit(f"expected exactly one tunnel-client executable, got {executables}")
(target/"agentos-tunnel-client-path").write_text(str(executables[0])+"\n", encoding="utf-8")
PY
TUNNEL_BIN="$(cat "$INSTALL_ROOT/agentos-tunnel-client-path")"
"$TUNNEL_BIN" --version

# Keep the OpenAI runtime credential in a dedicated file. Never place an
# OPENAI_ADMIN_KEY in this service: the daemon needs only Tunnels Read + Use.
umask 077
cat > "$ENV_FILE" <<EOF
CONTROL_PLANE_TUNNEL_ID=$TUNNEL_ID
CONTROL_PLANE_API_KEY=$RUNTIME_KEY
EOF
chmod 600 "$ENV_FILE"

cat > "$USER_SYSTEMD_DIR/agentos-chatgpt-openai-tunnel.service" <<EOF
[Unit]
Description=AgentOS ChatGPT OpenAI Secure MCP Tunnel
After=network-online.target agentos-chatgpt-mcp.service
Requires=agentos-chatgpt-mcp.service
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
ExecStart=$TUNNEL_BIN run --control-plane.tunnel-id \${CONTROL_PLANE_TUNNEL_ID} --mcp.server-url $MCP_URL --health.listen-addr 127.0.0.1:8781
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable agentos-chatgpt-openai-tunnel.service >/dev/null
systemctl --user restart agentos-chatgpt-openai-tunnel.service

READY=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if systemctl --user is-active --quiet agentos-chatgpt-openai-tunnel.service \
    && curl -fsS http://127.0.0.1:8781/readyz >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done
if [ "$READY" != "1" ]; then
  echo "openai_secure_mcp_tunnel_not_ready" >&2
  systemctl --user --no-pager --full status agentos-chatgpt-openai-tunnel.service >&2 || true
  journalctl --user -u agentos-chatgpt-openai-tunnel.service -n 120 --no-pager >&2 || true
  exit 7
fi

echo "openai_tunnel_binary_verified=ok"
echo "openai_tunnel_service=active"
echo "openai_tunnel_ready=ok"
echo "openai_tunnel_mcp_target=$MCP_URL"
echo "openai_tunnel_version=$VERSION"

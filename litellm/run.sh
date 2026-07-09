#!/bin/bash
# 🚀 AgentOS LiteLLM Companion Service Startup Script
# This script manages installing dependencies and starting the LiteLLM proxy in the background.

set -euo pipefail

# Navigate to the script directory to keep paths relative and portable
cd "$(dirname "$0")"
LITELLM_DIR=$(pwd)
REPO_ROOT=$(cd "$LITELLM_DIR/.." && pwd)
VENV_LITELLM="$REPO_ROOT/venv/bin/litellm"
LITELLM_BIN=""
SYSTEMD_UNIT="litellm"

# Load environment variables from repo root .env if it exists
if [ -f "$REPO_ROOT/.env" ]; then
    echo "🔑 [AgentOS LiteLLM] Loading environment variables from .env..."
    export $(grep -v '^#' "$REPO_ROOT/.env" | xargs)
fi

echo "🕸️  [AgentOS LiteLLM] Starting service initialization..."

# Prefer the user systemd unit when available so we don't accidentally leave
# behind a second background LiteLLM process on the same port.
if systemctl --user status "$SYSTEMD_UNIT" >/dev/null 2>&1; then
    echo "🛠️  [AgentOS LiteLLM] Found user systemd unit '$SYSTEMD_UNIT'. Restarting managed service..."
    systemctl --user restart "$SYSTEMD_UNIT"
    sleep 2

    if systemctl --user is-active --quiet "$SYSTEMD_UNIT"; then
        MAIN_PID=$(systemctl --user show "$SYSTEMD_UNIT" --property=MainPID --value)
        echo "✅ [AgentOS LiteLLM] systemd service is active. PID: $MAIN_PID"
        echo "📂 Logs are being written to: /home/dqa03/agent-data/logs/litellm.log"
        exit 0
    fi

    echo "❌ [AgentOS LiteLLM] systemd service failed to start."
    echo "   Check: systemctl --user status $SYSTEMD_UNIT --no-pager"
    exit 1
fi

# 1. Resolve LiteLLM executable
if [ -x "$VENV_LITELLM" ]; then
    LITELLM_BIN="$VENV_LITELLM"
elif command -v litellm &> /dev/null; then
    LITELLM_BIN=$(command -v litellm)
else
    export PATH="$HOME/.local/bin:$PATH"
    if command -v litellm &> /dev/null; then
        LITELLM_BIN=$(command -v litellm)
    fi
fi

if [ -z "$LITELLM_BIN" ]; then
    echo "❌ [AgentOS LiteLLM] LiteLLM executable not found."
    echo "   Expected repo venv binary at: $VENV_LITELLM"
    echo "   Activate/install LiteLLM in the repo virtualenv before starting the proxy."
    exit 1
fi

# 2. Handle Port conflict / Existing process cleanup
EXISTING_PID=$(pgrep -f "$LITELLM_BIN .*--config .*config.yml .*--port 4000" 2>/dev/null || true)
if [ -n "${EXISTING_PID:-}" ]; then
    echo "⚠️  [AgentOS LiteLLM] Found existing LiteLLM Proxy running at PID $EXISTING_PID. Restarting..."
    kill "$EXISTING_PID"
    sleep 1
fi

# Double check if port 4000 is still bound (force kill anything else on port 4000 if needed)
PORT_PID=$(lsof -t -i:4000 2>/dev/null || true)
if [ -n "${PORT_PID:-}" ]; then
    echo "⚠️  [AgentOS LiteLLM] Port 4000 is bound by PID $PORT_PID. Cleaning port..."
    kill "$PORT_PID"
    sleep 1
fi

# 3. Start LiteLLM Proxy in background
echo "🚀 [AgentOS LiteLLM] Starting LiteLLM Proxy on port 4000..."
# Unset DEBUG and LITELLM_MASTER_KEY for localhost dev mode.
nohup env -u DEBUG -u LITELLM_MASTER_KEY "$LITELLM_BIN" --config ./config.yml --host 127.0.0.1 --port 4000 > ./litellm.log 2>&1 &

# 4. Verify Startup success
sleep 2
NEW_PID=$(pgrep -f "$LITELLM_BIN .*--config .*config.yml .*--port 4000" 2>/dev/null || true)
if [ -n "${NEW_PID:-}" ]; then
    echo "✅ [AgentOS LiteLLM] Proxy started successfully! PID: $NEW_PID"
    echo "📂 Logs are being written to: $LITELLM_DIR/litellm.log"
else
    echo "❌ [AgentOS LiteLLM] Failed to start Proxy. Please check $LITELLM_DIR/litellm.log for details."
    exit 1
fi

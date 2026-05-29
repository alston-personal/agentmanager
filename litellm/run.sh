#!/bin/bash
# 🚀 AgentOS LiteLLM Companion Service Startup Script
# This script manages installing dependencies and starting the LiteLLM proxy in the background.

# Navigate to the script directory to keep paths relative and portable
cd "$(dirname "$0")"
LITELLM_DIR=$(pwd)

echo "🕸️  [AgentOS LiteLLM] Starting service initialization..."

# 1. Check Python dependencies
if ! python3 -c "import litellm" 2>/dev/null; then
    echo "📦 [AgentOS LiteLLM] Python package 'litellm' not found. Installing..."
    pip install 'litellm[proxy]' --user
fi

# 2. Check if LiteLLM executable is in PATH, if not add standard local bin paths
if ! command -v litellm &> /dev/null; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# 3. Handle Port conflict / Existing process cleanup
EXISTING_PID=$(pgrep -f "litellm --config .*config.yml --port 4000" 2>/dev/null)
if [ ! -z "$EXISTING_PID" ]; then
    echo "⚠️  [AgentOS LiteLLM] Found existing LiteLLM Proxy running at PID $EXISTING_PID. Restarting..."
    kill -9 "$EXISTING_PID"
    sleep 1
fi

# Double check if port 4000 is still bound (force kill anything else on port 4000 if needed)
PORT_PID=$(lsof -t -i:4000 2>/dev/null)
if [ ! -z "$PORT_PID" ]; then
    echo "⚠️  [AgentOS LiteLLM] Port 4000 is bound by PID $PORT_PID. Cleaning port..."
    kill -9 "$PORT_PID"
    sleep 1
fi

# 4. Start LiteLLM Proxy in background
echo "🚀 [AgentOS LiteLLM] Starting LiteLLM Proxy on port 4000..."
nohup litellm --config ./config.yml --port 4000 > ./litellm.log 2>&1 &

# 5. Verify Startup success
sleep 2
NEW_PID=$(pgrep -f "litellm --config .*config.yml --port 4000" 2>/dev/null)
if [ ! -z "$NEW_PID" ]; then
    echo "✅ [AgentOS LiteLLM] Proxy started successfully! PID: $NEW_PID"
    echo "📂 Logs are being written to: $LITELLM_DIR/litellm.log"
else
    echo "❌ [AgentOS LiteLLM] Failed to start Proxy. Please check $LITELLM_DIR/litellm.log for details."
    exit 1
fi

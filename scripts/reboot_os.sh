#!/bin/bash
# 🛰️ AgentOS Global Reboot Protocol (v0.6.3-ConfigDriven)

# Locate Self
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load Persistence Layer Path from .env
if [ -f "$LOGIC_ROOT/.env" ]; then
    export $(grep -v '^#' "$LOGIC_ROOT/.env" | grep "AGENT_DATA_DIR" | xargs)
fi

# Final Fallback Resolution
DATA_ROOT="${AGENT_DATA_DIR:-$HOME/agent-data}"

echo "🌅 [Resurrection] Initializing AgentOS..."
echo "📍 Data Center Defined at: $DATA_ROOT"

# Check if data exists
if [ ! -d "$DATA_ROOT" ]; then
    echo "❌ FATAL: Data Center NOT FOUND at $DATA_ROOT"
    exit 1
fi

# Re-link for the current environment
ln -nfs "$DATA_ROOT/memory" "$LOGIC_ROOT/memory"
ln -nfs "$DATA_ROOT/logs" "$LOGIC_ROOT/logs"
ln -nfs "$DATA_ROOT/projects" "$LOGIC_ROOT/projects"

# Restart core services
systemctl --user daemon-reload
systemctl --user restart tg-commander.service 2>/dev/null || echo "⚠️ Service ignored (Non-server mode)."

echo "🔍 Memory Recall..."
$LOGIC_ROOT/scripts/recall_chronicle.py

echo "✅ AgentOS Stable."

#!/bin/bash
# 🧠 AgentOS Brain-Sync Utility (v1.0.0)
# Purpose: Synchronize both Logic and Data layers to ensure system-wide consistency.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load Environment to find DATA_ROOT
if [ -f "$LOGIC_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$LOGIC_ROOT/.env"
    set +a
fi
DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"

echo "🔄 [Sync] Starting Global Synchronization..."

# 1. Sync Logic Layer (agentmanager)
echo "📍 Sector: Logic ($LOGIC_ROOT)"
cd "$LOGIC_ROOT"
if [ -d ".git" ]; then
    git pull --rebase
    echo "✅ Logic synced."
else
    echo "⚠️ Logic folder is not a git repo. Skipping."
fi

# 2. Sync Data Layer (agent-data)
echo "📍 Sector: Data ($DATA_ROOT)"
cd "$DATA_ROOT"
if [ -d ".git" ]; then
    git pull --rebase
    echo "✅ Data synced."
else
    echo "⚠️ Data folder is not a git repo. Skipping."
fi

# 3. Validation & Health Check
echo "🩺 [Health Check] Verifying integrity..."
/bin/bash "$LOGIC_ROOT/scripts/health_check.sh"

echo "🏆 Sync Complete. Your consciousness is now aligned across the dimensions."

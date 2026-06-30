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
    # Check for changes (tracked or untracked)
    if [ -n "$(git status --porcelain)" ]; then
        echo "📝 Found local changes in Data Layer. Committing..."
        git add -A
        git commit -m "chore(sync): automated sync of status and logs at $(date '+%Y-%m-%d %H:%M:%S')"
    fi
    echo "⬇️ Pulling latest changes..."
    git pull --rebase
    
    # Check if we have commits to push (local is ahead of origin)
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")
    if [ "$LOCAL" != "$REMOTE" ]; then
        echo "⬆️ Pushing changes to remote..."
        git push origin main
    fi
    echo "✅ Data synced."
else
    echo "⚠️ Data folder is not a git repo. Skipping."
fi

# 3. Validation & Health Check
echo "🩺 [Health Check] Verifying integrity..."
/bin/bash "$LOGIC_ROOT/scripts/health_check.sh"

echo "🏆 Sync Complete. Your consciousness is now aligned across the dimensions."

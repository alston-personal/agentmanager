#!/bin/bash
# 🛰️ AgentOS Global Reboot Protocol (v0.6.4-AutoSelfHealing)

# 📍 1. Locate Environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 🧪 2. Config Auditor (Auto-Heal .env)
if [ ! -f "$LOGIC_ROOT/.env" ]; then
    echo "⚠️ .env NOT FOUND. Creating from example..."
    cp "$LOGIC_ROOT/.env.example" "$LOGIC_ROOT/.env"
else
    # Audit for missing keys from example
    while read -r line || [[ -n "$line" ]]; do
        key=$(echo "$line" | cut -d'=' -f1)
        if [[ ! -z "$key" && "$key" != \#* ]]; then
            if ! grep -q "^$key=" "$LOGIC_ROOT/.env"; then
                echo "🪄 Added missing config key: $key"
                echo "$line" >> "$LOGIC_ROOT/.env"
            fi
        fi
    done < "$LOGIC_ROOT/.env.example"
fi

# 📍 3. Load Persistence Layer Path
set -a
source "$LOGIC_ROOT/.env"
set +a
DATA_ROOT="${AGENT_DATA_DIR:-$HOME/agent-data}"

echo "🌅 [Resurrection] Initializing AgentOS..."
echo "📍 Data Center: $DATA_ROOT"

# Check if data exists
if [ ! -d "$DATA_ROOT" ]; then
    echo "❌ FATAL: Data Center NOT FOUND at $DATA_ROOT"
    echo "💡 Please edit .env and set AGENT_DATA_DIR to your real path."
    exit 1
fi

# 🔗 4. Re-link Bridges (Relative to logic root)
ln -nfs "$DATA_ROOT/memory" "$LOGIC_ROOT/memory"
ln -nfs "$DATA_ROOT/logs" "$LOGIC_ROOT/logs"
ln -nfs "$DATA_ROOT/projects" "$LOGIC_ROOT/projects"
ln -nfs "$DATA_ROOT/ARCHITECTURE.md" "$LOGIC_ROOT/ARCHITECTURE.md"

# 🧠 4b. Re-link Knowledge Bridge (Two-layer chain)
# Layer 1: agent-data/knowledge → antigravity/knowledge (IDE Knowledge Base)
ANTIGRAVITY_DIR="$HOME/.gemini/antigravity"
if [ -d "$ANTIGRAVITY_DIR" ]; then
    ln -nfs "$DATA_ROOT/knowledge" "$ANTIGRAVITY_DIR/knowledge"
    echo "🔗 Knowledge bridge restored: $ANTIGRAVITY_DIR/knowledge → $DATA_ROOT/knowledge"
fi
# Layer 2: agentmanager/knowledge → antigravity/knowledge
ln -nfs "$ANTIGRAVITY_DIR/knowledge" "$LOGIC_ROOT/knowledge"
echo "🔗 Knowledge bridge restored: $LOGIC_ROOT/knowledge → $ANTIGRAVITY_DIR/knowledge"

# ⚡ 5. Restart Services
systemctl --user daemon-reload
if [ "$AGENT_MODE" == "CORE" ]; then
    echo "⚡ [Core Mode] Restarting command bridge..."
    systemctl --user restart tg-commander.service 2>/dev/null || echo "⚠️ Service ignored (Non-server mode)."
else
    echo "🕶️ [Client Mode] Skipping service restart."
fi

# 🔍 6. Memory Recall
$LOGIC_ROOT/scripts/recall_chronicle.py

echo "✅ AgentOS Stable."

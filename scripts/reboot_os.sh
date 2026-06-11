#!/bin/bash
# 🛰️ AgentOS Global Reboot Protocol (v0.6.4-AutoSelfHealing)
export PYTHONUTF8=1

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
[ -f "$HOME/.agentos.secrets" ] && source "$HOME/.agentos.secrets"
set +a
DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
AGENT_DATA_ROOT="$DATA_ROOT"
AGENT_DATA_DIR="$DATA_ROOT"
ANTIGRAVITY_DIR="${ANTIGRAVITY_DIR:-$HOME/.gemini/antigravity}"
KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT:-$ANTIGRAVITY_DIR/knowledge}"

echo "🌅 [Resurrection] Initializing AgentOS..."
echo "📍 Data Center: $DATA_ROOT"

link_bridge() {
    local source_path="$1"
    local target_path="$2"

    if [ -L "$target_path" ] || [ ! -e "$target_path" ]; then
        if [[ "$OSTYPE" == "msys" ]]; then
            rm -f "$target_path" 2>/dev/null || rmdir "$target_path" 2>/dev/null
            local win_source=$(cygpath -w "$source_path")
            local win_target=$(cygpath -w "$target_path")
            cmd //c mklink //j "$win_target" "$win_source"
        else
            ln -nfs "$source_path" "$target_path"
        fi
        return
    fi

    if [ -d "$target_path" ]; then
        mkdir -p "$source_path"
        cp -an "$target_path/." "$source_path/" 2>/dev/null || true
    fi

    local backup_path="${target_path}.pre-agentos-link.$(date +%Y%m%d%H%M%S)"
    mv "$target_path" "$backup_path"
    
    if [[ "$OSTYPE" == "msys" ]]; then
        local win_source=$(cygpath -w "$source_path")
        local win_target=$(cygpath -w "$target_path")
        cmd //c mklink //j "$win_target" "$win_source"
    else
        ln -s "$source_path" "$target_path"
    fi
    echo "📦 Backed up existing bridge target: $backup_path"
}

# Check if data exists
if [ ! -d "$DATA_ROOT" ]; then
    echo "❌ FATAL: Data Center NOT FOUND at $DATA_ROOT"
    echo "💡 Please edit .env and set AGENT_DATA_ROOT to your real path."
    exit 1
fi

# 🔗 4. Re-link Bridges (Relative to logic root)
mkdir -p "$DATA_ROOT/memory" "$DATA_ROOT/logs" "$DATA_ROOT/projects"
mkdir -p "$DATA_ROOT/knowledge"
if [ -L "$DATA_ROOT/knowledge/knowledge" ] && [ "$(readlink "$DATA_ROOT/knowledge/knowledge")" = "$DATA_ROOT/knowledge" ]; then
    unlink "$DATA_ROOT/knowledge/knowledge"
fi
link_bridge "$DATA_ROOT/memory" "$LOGIC_ROOT/memory"
link_bridge "$DATA_ROOT/logs" "$LOGIC_ROOT/logs"
link_bridge "$DATA_ROOT/projects" "$LOGIC_ROOT/projects"

if [[ "$OSTYPE" == "msys" ]]; then
    rm -f "$LOGIC_ROOT/ARCHITECTURE.md" 2>/dev/null
    win_source=$(cygpath -w "$DATA_ROOT/ARCHITECTURE.md")
    win_target=$(cygpath -w "$LOGIC_ROOT/ARCHITECTURE.md")
    cmd //c mklink //h "$win_target" "$win_source" 2>/dev/null || cp "$DATA_ROOT/ARCHITECTURE.md" "$LOGIC_ROOT/ARCHITECTURE.md"
else
    ln -nfs "$DATA_ROOT/ARCHITECTURE.md" "$LOGIC_ROOT/ARCHITECTURE.md"
fi

# 🧠 4b. Re-link Knowledge Bridge (Two-layer chain)
# Layer 1: agent-data/knowledge → antigravity/knowledge (IDE Knowledge Base)
if [ -d "$ANTIGRAVITY_DIR" ]; then
    mkdir -p "$KNOWLEDGE_ROOT" "$DATA_ROOT/knowledge"
    if [ "$KNOWLEDGE_ROOT" != "$DATA_ROOT/knowledge" ] && [ -d "$KNOWLEDGE_ROOT" ] && [ ! -L "$KNOWLEDGE_ROOT" ]; then
        cp -an "$KNOWLEDGE_ROOT/." "$DATA_ROOT/knowledge/" 2>/dev/null || true
    fi
    link_bridge "$DATA_ROOT/knowledge" "$ANTIGRAVITY_DIR/knowledge"
    echo "🔗 Knowledge bridge restored: $ANTIGRAVITY_DIR/knowledge -> $DATA_ROOT/knowledge"
fi
# Layer 2: agentmanager/knowledge → antigravity/knowledge
link_bridge "$DATA_ROOT/knowledge" "$LOGIC_ROOT/knowledge"
echo "🔗 Knowledge bridge restored: $LOGIC_ROOT/knowledge -> $DATA_ROOT/knowledge"

# ⚡ 5. Restart Services
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload
    if [ "$AGENT_MODE" == "CORE" ]; then
        echo "⚡ [Core Mode] Restarting command bridge..."
        systemctl --user restart tg-commander.service 2>/dev/null || echo "⚠️ Service ignored (Non-server mode)."
    else
        echo "🕶️ [Client Mode] Skipping service restart."
    fi
else
    echo "🕶️ [Non-Systemd Environment] Skipping systemctl services reload."
fi

# 🔍 6. Memory Recall
if [ -f "$LOGIC_ROOT/venv/Scripts/python" ]; then
    "$LOGIC_ROOT/venv/Scripts/python" "$LOGIC_ROOT/scripts/recall_chronicle.py"
elif [ -f "$LOGIC_ROOT/venv/bin/python3" ]; then
    "$LOGIC_ROOT/venv/bin/python3" "$LOGIC_ROOT/scripts/recall_chronicle.py"
elif [ -f "$LOGIC_ROOT/.venv/Scripts/python" ]; then
    "$LOGIC_ROOT/.venv/Scripts/python" "$LOGIC_ROOT/scripts/recall_chronicle.py"
elif [ -f "$LOGIC_ROOT/.venv/bin/python3" ]; then
    "$LOGIC_ROOT/.venv/bin/python3" "$LOGIC_ROOT/scripts/recall_chronicle.py"
else
    python3 "$LOGIC_ROOT/scripts/recall_chronicle.py" || python "$LOGIC_ROOT/scripts/recall_chronicle.py" || "$LOGIC_ROOT/scripts/recall_chronicle.py"
fi

echo "✅ AgentOS Stable."

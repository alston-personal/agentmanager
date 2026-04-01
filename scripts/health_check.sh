#!/bin/bash
# 🏥 AgentOS Global Health Check (v0.6.1-Portable)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_ROOT="$(cd "$LOGIC_ROOT/../agent-data" 2>/dev/null && pwd || echo "$HOME/agent-data")"

echo "🌡️ [Diagnostic] Checking AgentOS Integrity..."
echo "📍 Working from: $LOGIC_ROOT"

# Check Core Symlinks
items=("memory" "logs" "projects" "ARCHITECTURE.md")
for item in "\${items[@]}"; do
    if [ -L "$LOGIC_ROOT/\$item" ]; then
        echo "✅ Symlink OK: \$item -> $(readlink "$LOGIC_ROOT/\$item")"
    else
        echo "❌ Symlink BROKEN: \$item"
    fi
done

# Check Services
echo "⚙️ Checking Services..."
systemctl --user is-active tg-commander.service || echo "⚠️ tg-commander is NOT running."
systemctl --user is-active os-pulse.service || echo "⚠️ os-pulse is NOT running."

echo "🏆 Diagnostic Complete."

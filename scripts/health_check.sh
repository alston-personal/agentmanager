#!/bin/bash
# 🏥 AgentOS Global Health Check (v0.6.2-Portable)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🌡️ [Diagnostic] Checking AgentOS Integrity..."
items=("memory" "logs" "projects" "projects_status" "knowledge" "ARCHITECTURE.md")

for item in "${items[@]}"; do
    if [ -L "$LOGIC_ROOT/$item" ]; then
        TARGET=$(readlink "$LOGIC_ROOT/$item")
        echo "✅ Symlink OK: $item -> $TARGET"
    else
        echo "❌ Symlink BROKEN or MISSING: $item"
    fi
done

echo "⚙️ Checking Services..."
systemctl --user is-active tg-commander.service || echo "⚠️ tg-commander is NOT running."
systemctl --user is-active os-pulse.service || echo "⚠️ os-pulse is NOT running."

echo "🏆 Diagnostic Complete."

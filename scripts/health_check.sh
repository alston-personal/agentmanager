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
if [ -f "$LOGIC_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$LOGIC_ROOT/.env"
    set +a
fi

systemctl --user is-active os-pulse.service || echo "⚠️ os-pulse is NOT running."

if [ "${AGENT_MODE:-CLIENT}" = "CORE" ]; then
    systemctl --user is-active tg-commander.service || echo "⚠️ tg-commander is NOT running."
    systemctl --user is-active cat-ink-syncer.service || echo "⚠️ cat-ink-syncer is NOT running."
else
    echo "🕶️ Client mode: core-only services are optional."
fi

echo "🏆 Diagnostic Complete."

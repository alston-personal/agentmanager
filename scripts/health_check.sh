#!/bin/bash
# 🏥 AgentOS Global Health Check (v0.6.2-Portable)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGIC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$LOGIC_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$LOGIC_ROOT/.env"
    set +a
fi
DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"

echo "🌡️ [Diagnostic] Checking AgentOS Integrity..."
issues=0
declare -A expected_targets=(
    ["memory"]="$DATA_ROOT/memory"
    ["logs"]="$DATA_ROOT/logs"
    ["projects"]="$DATA_ROOT/projects"
    ["projects_status"]="$DATA_ROOT/projects"
    ["knowledge"]="$DATA_ROOT/knowledge"
    ["ARCHITECTURE.md"]="$DATA_ROOT/ARCHITECTURE.md"
)

items=("memory" "logs" "projects" "projects_status" "knowledge" "ARCHITECTURE.md")

for item in "${items[@]}"; do
    link_path="$LOGIC_ROOT/$item"
    expected="${expected_targets[$item]}"
    if [ -L "$link_path" ]; then
        target="$(readlink "$link_path")"
        if [ "$target" = "$expected" ]; then
            echo "✅ Symlink OK: $item -> $target"
        else
            echo "❌ Symlink WRONG: $item -> $target (expected $expected)"
            issues=$((issues + 1))
        fi
    else
        echo "❌ Symlink BROKEN or MISSING: $item"
        issues=$((issues + 1))
    fi
done

echo "⚙️ Checking Services..."

check_required_service() {
    local service_name="$1"
    if systemctl --user is-active --quiet "$service_name"; then
        echo "✅ Service active: $service_name"
    else
        echo "⚠️ $service_name is NOT running."
        issues=$((issues + 1))
    fi
}

if [ "${AGENT_MODE:-CLIENT}" = "CORE" ]; then
    check_required_service os-pulse.service
    check_required_service tg-commander.service
    check_required_service cat-ink-syncer.service
else
    if systemctl --user is-active --quiet os-pulse.service; then
        echo "✅ Service active: os-pulse.service"
    else
        echo "ℹ️ os-pulse is not running on this client."
    fi
    echo "🕶️ Client mode: core-only services are optional."
fi

if [ "$issues" -gt 0 ]; then
    echo "⚠️ Diagnostic completed with $issues issue(s)."
    exit 1
fi

echo "🏆 Diagnostic Complete."

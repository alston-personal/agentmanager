#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${AGENT_PROJECT_ROOT:-$(pwd)}"
AGENT_DATA_ROOT="${AGENT_DATA_ROOT:-$HOME/agent-data}"

echo "Using AGENT_DATA_ROOT=$AGENT_DATA_ROOT"

mkdir -p "$AGENT_DATA_ROOT/memory"
mkdir -p "$AGENT_DATA_ROOT/projects/agentmanager"

ln -sfn "$AGENT_DATA_ROOT/memory" "$PROJECT_ROOT/memory"
ln -sfn "$AGENT_DATA_ROOT/projects/agentmanager/STATUS.md" "$PROJECT_ROOT/STATUS.md"
mkdir -p "$PROJECT_ROOT/.agent/memory"
ln -sfn "$AGENT_DATA_ROOT/memory/session_sync.md" "$PROJECT_ROOT/.agent/memory/session_sync.md"

echo "Linked:"
ls -ld "$PROJECT_ROOT/memory" "$PROJECT_ROOT/STATUS.md" "$PROJECT_ROOT/.agent/memory/session_sync.md"
echo "Done."

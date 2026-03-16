#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/ubuntu/agentmanager"
AGENT_DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"

echo "Using AGENT_DATA_ROOT=$AGENT_DATA_ROOT"

mkdir -p "$AGENT_DATA_ROOT/memory"
mkdir -p "$AGENT_DATA_ROOT/projects/ai-command-center"

ln -sfn "$AGENT_DATA_ROOT/memory" "$PROJECT_ROOT/memory"
ln -sfn "$AGENT_DATA_ROOT/projects/ai-command-center/STATUS.md" "$PROJECT_ROOT/STATUS.md"
mkdir -p "$PROJECT_ROOT/.agent/memory"
ln -sfn "$AGENT_DATA_ROOT/memory/session_sync.md" "$PROJECT_ROOT/.agent/memory/session_sync.md"

echo "Linked:"
ls -ld "$PROJECT_ROOT/memory" "$PROJECT_ROOT/STATUS.md" "$PROJECT_ROOT/.agent/memory/session_sync.md"
echo "Done."

#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${AGENT_PROJECT_ROOT:-$(pwd)}"
ENV_FILE="${PROJECT_ROOT}/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

AGENT_DATA_ROOT="${AGENT_DATA_ROOT:-${AGENT_DATA_DIR:-$HOME/agent-data}}"
ANTIGRAVITY_DIR="${ANTIGRAVITY_DIR:-$HOME/.gemini/antigravity}"
KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT:-$ANTIGRAVITY_DIR/knowledge}"

link_bridge() {
  local source_path="$1"
  local target_path="$2"

  if [ -L "$target_path" ] || [ ! -e "$target_path" ]; then
    ln -sfn "$source_path" "$target_path"
    return
  fi

  if [ -d "$target_path" ]; then
    mkdir -p "$source_path"
    cp -an "$target_path/." "$source_path/" 2>/dev/null || true
  fi

  local backup_path="${target_path}.pre-agentos-link.$(date +%Y%m%d%H%M%S)"
  mv "$target_path" "$backup_path"
  ln -s "$source_path" "$target_path"
  echo "Backed up existing bridge target: $backup_path"
}

echo "Using AGENT_DATA_ROOT=$AGENT_DATA_ROOT"

mkdir -p "$AGENT_DATA_ROOT/memory"
mkdir -p "$AGENT_DATA_ROOT/projects/agentmanager"
mkdir -p "$AGENT_DATA_ROOT/logs"
mkdir -p "$AGENT_DATA_ROOT/knowledge"
if [ -L "$AGENT_DATA_ROOT/knowledge/knowledge" ] && [ "$(readlink "$AGENT_DATA_ROOT/knowledge/knowledge")" = "$AGENT_DATA_ROOT/knowledge" ]; then
  unlink "$AGENT_DATA_ROOT/knowledge/knowledge"
fi

link_bridge "$AGENT_DATA_ROOT/memory" "$PROJECT_ROOT/memory"
link_bridge "$AGENT_DATA_ROOT/projects" "$PROJECT_ROOT/projects"
link_bridge "$AGENT_DATA_ROOT/logs" "$PROJECT_ROOT/logs"
link_bridge "$AGENT_DATA_ROOT/knowledge" "$PROJECT_ROOT/knowledge"
if [ -f "$AGENT_DATA_ROOT/projects/agentmanager/STATUS.md" ]; then
  ln -sfn "$AGENT_DATA_ROOT/projects/agentmanager/STATUS.md" "$PROJECT_ROOT/STATUS.md"
fi
mkdir -p "$PROJECT_ROOT/.agent/memory"
ln -sfn "$AGENT_DATA_ROOT/memory/session_sync.md" "$PROJECT_ROOT/.agent/memory/session_sync.md"
if [ -d "$ANTIGRAVITY_DIR" ]; then
  mkdir -p "$KNOWLEDGE_ROOT"
  if [ "$KNOWLEDGE_ROOT" != "$AGENT_DATA_ROOT/knowledge" ] && [ -d "$KNOWLEDGE_ROOT" ] && [ ! -L "$KNOWLEDGE_ROOT" ]; then
    cp -an "$KNOWLEDGE_ROOT/." "$AGENT_DATA_ROOT/knowledge/" 2>/dev/null || true
  fi
  link_bridge "$AGENT_DATA_ROOT/knowledge" "$ANTIGRAVITY_DIR/knowledge"
fi

echo "Linked:"
ls -ld "$PROJECT_ROOT/memory" "$PROJECT_ROOT/projects" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/knowledge" "$PROJECT_ROOT/.agent/memory/session_sync.md"
echo "Done."

#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: Oracle Antigravity ONE bootstrap must run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
RUNTIME_ROOT="${AGENTOS_ONE_MCP_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/one-mcp-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }
test -f "$DATA_ROOT/realm/nodes.json" || { echo "ERROR: Oracle ONE Node Registry missing" >&2; exit 4; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"

if [ ! -f "$TARGET/agentos_node/one_mcp.py" ]; then
  TMP="$RUNTIME_ROOT/.install-$SOURCE_COMMIT-$$"
  rm -rf "$TMP"
  mkdir -p "$TMP" "$RUNTIME_ROOT"
  git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$TMP"
  mv "$TMP" "$TARGET"
fi

CORE_PROJECT="$DATA_ROOT/projects/agentos-core"
EXECUTION_HEAD="$CORE_PROJECT/execution-head.json"
CONTINUATION_HEAD="$CORE_PROJECT/continuity/latest.json"

if [ ! -e "$EXECUTION_HEAD" ] && [ ! -e "$CONTINUATION_HEAD" ]; then
  echo "agentos_core_ir_seed=REQUIRED"
  PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
    python3 "$TARGET/scripts/seed_agentos_core_ir_head.py"
elif [ -e "$EXECUTION_HEAD" ] && [ -e "$CONTINUATION_HEAD" ]; then
  echo "agentos_core_ir_seed=SKIPPED_EXISTING_HEAD"
else
  echo "ERROR: partial AgentOS Core canonical head exists; refusing to overwrite" >&2
  echo "execution_head_exists=$([ -e "$EXECUTION_HEAD" ] && echo YES || echo NO)" >&2
  echo "continuation_head_exists=$([ -e "$CONTINUATION_HEAD" ] && echo YES || echo NO)" >&2
  exit 5
fi

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/install_antigravity_one_mcp_oracle.py"

echo "agentos_antigravity_one_bootstrap=PASS"
echo "agentos_source_ref=$SOURCE_REF"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "agentos_runtime_source=$TARGET"
echo "antigravity_reload_required=YES"

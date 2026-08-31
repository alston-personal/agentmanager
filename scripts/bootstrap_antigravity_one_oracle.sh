#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: Oracle Antigravity ONE bootstrap must run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
RUNTIME_ROOT="${AGENTOS_ONE_MCP_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/one-mcp-source}"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }
test -f "/home/ubuntu/agent-data/realm/nodes.json" || { echo "ERROR: Oracle ONE Node Registry missing" >&2; exit 4; }

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

python3 "$TARGET/scripts/install_antigravity_one_mcp_oracle.py"

echo "agentos_antigravity_one_bootstrap=PASS"
echo "agentos_source_ref=$SOURCE_REF"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "agentos_runtime_source=$TARGET"
echo "antigravity_reload_required=YES"

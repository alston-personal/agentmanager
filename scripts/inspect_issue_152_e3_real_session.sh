#!/usr/bin/env bash
set -euo pipefail

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
RUNTIME_ROOT="${AGENTOS_ONE_MCP_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/one-mcp-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF" >/dev/null
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"
INSPECTOR="$TARGET/scripts/inspect_antigravity_preinvocation_attestation.py"

echo "agentos_e3_expected_runtime_commit=$SOURCE_COMMIT"
echo "agentos_e3_expected_runtime_source=$TARGET"

test -f "$INSPECTOR" || {
  echo "ERROR: latest attestation inspector is not installed at $INSPECTOR" >&2
  echo "Run the E3 preparation helper once, reload Antigravity, then retry the fresh Codex session." >&2
  exit 4
}

cd "$TARGET"
set +e
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$INSPECTOR"
RC=$?
set -e

case "$RC" in
  0)
    echo "agentos_e3_real_session_hook=FIRED_AND_HYDRATED"
    ;;
  4)
    echo "agentos_e3_real_session_hook=NOT_PROVEN"
    ;;
  *)
    echo "agentos_e3_real_session_hook=INSPECTION_ERROR"
    ;;
esac
exit "$RC"

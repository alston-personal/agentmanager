#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: #185 Claude extension preparation must run as ubuntu on Oracle" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-185-claude-extension-one"
RUNTIME_ROOT="${AGENTOS_CLAUDE_ONE_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/claude-one-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
EXPECTED_INDEX="idx-core-185-claude-ext-1"
EXPECTED_IR="ir-core-185-claude-ext-1"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }
test -f "$DATA_ROOT/runtime/active-continuation.json" || { echo "ERROR: ONE active continuation selector missing" >&2; exit 4; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"

if [ ! -f "$TARGET/scripts/install_claude_one_oracle.py" ]; then
  TMP="$RUNTIME_ROOT/.claude-e185-$SOURCE_COMMIT-$$"
  rm -rf "$TMP"
  mkdir -p "$TMP" "$RUNTIME_ROOT"
  git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$TMP"
  mv "$TMP" "$TARGET"
fi

cd "$TARGET"
echo "agentos_claude_e185_source_commit=$SOURCE_COMMIT"
echo "agentos_claude_e185_runtime_source=$TARGET"
echo "agentos_claude_e185_execution_cwd=$PWD"

echo "agentos_claude_e185_contract_tests=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 -m unittest \
    tests.test_project_continuation_index \
    tests.test_canonical_ir_handoff \
    tests.test_active_continuation \
    tests.test_claude_one_mcp_stdio \
    tests.test_install_claude_one_oracle \
    -v
echo "agentos_claude_e185_contract_tests=PASS"

read -r ACTIVE_PROJECT ACTIVE_INDEX ACTIVE_IR < <(
  PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" python3 - <<'PY'
from agent_core.active_continuation import resolve_active_continuation
import os
from pathlib import Path
r = resolve_active_continuation(data_root=Path(os.environ["AGENT_DATA_ROOT"]))
s = r.get("selector") or {}
print(s.get("project_id") or "", s.get("index_id") or "", s.get("ir_id") or "")
PY
)

if [ "$ACTIVE_PROJECT" != "agentos-core" ]; then
  echo "ERROR: active project is not agentos-core: $ACTIVE_PROJECT" >&2
  exit 5
fi

echo "agentos_claude_e185_parent_index=$ACTIVE_INDEX"
echo "agentos_claude_e185_parent_ir=$ACTIVE_IR"
echo "agentos_claude_e185_canonical_handoff=RUNNING"
PYTHONPATH="$TARGET" \
AGENT_DATA_ROOT="$DATA_ROOT" \
AGENTOS_EXPECTED_PARENT_INDEX="$ACTIVE_INDEX" \
AGENTOS_EXPECTED_PARENT_IR="$ACTIVE_IR" \
  python3 "$TARGET/scripts/advance_issue_185_to_claude_extension.py"
echo "agentos_claude_e185_canonical_handoff=PASS"

echo "agentos_claude_e185_install=RUNNING"
PYTHONPATH="$TARGET" \
AGENT_DATA_ROOT="$DATA_ROOT" \
AGENTOS_RUNTIME_SOURCE_COMMIT="$SOURCE_COMMIT" \
  python3 "$TARGET/scripts/install_claude_one_oracle.py"
echo "agentos_claude_e185_install=PASS"

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" python3 - <<'PY'
import json
from agentos_node.claude_one_mcp_stdio import _active_projection
from agentos_node.one_mcp import OracleLocalGateway

result = _active_projection(OracleLocalGateway())
selector = result.get("selector") or {}
if selector.get("project_id") != "agentos-core":
    raise SystemExit(f"Claude active project mismatch: {selector}")
if selector.get("index_id") != "idx-core-185-claude-ext-1" or selector.get("ir_id") != "ir-core-185-claude-ext-1":
    raise SystemExit(f"Claude active generation mismatch: {selector}")
if result.get("credential_exposed") is not False:
    raise SystemExit("Claude ONE credential isolation not proven")
print(json.dumps({
    "schema": "agentos.issue-185-claude-extension-probe/v1",
    "ok": True,
    "source": result.get("source"),
    "selection_source": result.get("selection_source"),
    "surface": result.get("surface"),
    "executor_adapter": result.get("executor_adapter"),
    "executor_class": result.get("executor_class"),
    "backend_class": result.get("backend_class"),
    "backend_identity": result.get("backend_identity"),
    "backend_identity_bound": result.get("backend_identity_bound"),
    "project_id": selector.get("project_id"),
    "index_id": selector.get("index_id"),
    "ir_id": selector.get("ir_id"),
    "credential_exposed": result.get("credential_exposed"),
}, ensure_ascii=False, indent=2, sort_keys=True))
PY

echo "agentos_issue_185_claude_extension=PREPARED"
echo "agentos_claude_e185_index_id=$EXPECTED_INDEX"
echo "agentos_claude_e185_ir_id=$EXPECTED_IR"
echo "claude_extension_reload_required=YES"

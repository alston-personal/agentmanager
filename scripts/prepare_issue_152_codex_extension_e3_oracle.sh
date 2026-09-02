#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: #152 Codex extension E3 preparation must run as ubuntu on Oracle" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
RUNTIME_ROOT="${AGENTOS_ONE_MCP_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/one-mcp-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
EXPECTED_INDEX="idx-core-152-e3-codex-ext-1"
EXPECTED_IR="ir-core-152-e3-codex-ext-1"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }
test -f "$DATA_ROOT/realm/nodes.json" || { echo "ERROR: Oracle ONE Node Registry missing" >&2; exit 4; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"

if [ ! -f "$TARGET/scripts/install_codex_one_oracle.py" ]; then
  TMP="$RUNTIME_ROOT/.codex-e3-$SOURCE_COMMIT-$$"
  rm -rf "$TMP"
  mkdir -p "$TMP" "$RUNTIME_ROOT"
  git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$TMP"
  mv "$TMP" "$TARGET"
fi

cd "$TARGET"
echo "agentos_codex_e3_source_commit=$SOURCE_COMMIT"
echo "agentos_codex_e3_runtime_source=$TARGET"
echo "agentos_codex_e3_execution_cwd=$PWD"

echo "agentos_codex_e3_contract_tests=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 -m unittest \
    tests.test_project_continuation_index \
    tests.test_canonical_ir_handoff \
    tests.test_active_continuation \
    tests.test_codex_one_mcp_stdio \
    -v
echo "agentos_codex_e3_contract_tests=PASS"

echo "agentos_codex_e3_canonical_handoff=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/advance_issue_152_e3_to_codex_extension.py"
echo "agentos_codex_e3_canonical_handoff=PASS"

echo "agentos_codex_e3_install=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/install_codex_one_oracle.py"
echo "agentos_codex_e3_install=PASS"

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 - <<'PY'
import json
import os
from agentos_node.codex_one_mcp_stdio import _active_projection
from agentos_node.one_mcp import OracleLocalGateway

expected_index = "idx-core-152-e3-codex-ext-1"
expected_ir = "ir-core-152-e3-codex-ext-1"
result = _active_projection(OracleLocalGateway())
selector = result.get("selector") or {}
if selector.get("project_id") != "agentos-core":
    raise SystemExit(f"Codex active project mismatch: {selector}")
if selector.get("index_id") != expected_index or selector.get("ir_id") != expected_ir:
    raise SystemExit(f"Codex active generation mismatch: {selector}")
print(json.dumps({
    "schema": "agentos.issue-152-codex-extension-probe/v1",
    "ok": True,
    "source": result.get("source"),
    "selection_source": result.get("selection_source"),
    "surface": result.get("surface"),
    "executor_class": result.get("executor_class"),
    "project_id": selector.get("project_id"),
    "index_id": selector.get("index_id"),
    "ir_id": selector.get("ir_id"),
    "credential_exposed": result.get("credential_exposed"),
}, ensure_ascii=False, indent=2, sort_keys=True))
PY

echo "agentos_issue_152_codex_extension_e3=PASS"
echo "agentos_codex_e3_index_id=$EXPECTED_INDEX"
echo "agentos_codex_e3_ir_id=$EXPECTED_IR"
echo "codex_extension_reload_required=YES"

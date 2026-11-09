#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: #152 post-E3 advancement must run as ubuntu on Oracle" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
RUNTIME_ROOT="${AGENTOS_ONE_MCP_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/one-mcp-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
EXPECTED_INDEX="idx-core-152-post-e3-1"
EXPECTED_IR="ir-core-152-post-e3-1"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }
test -f "$DATA_ROOT/realm/nodes.json" || { echo "ERROR: Oracle ONE Node Registry missing" >&2; exit 4; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"

if [ ! -f "$TARGET/scripts/advance_issue_152_after_e3_verified.py" ]; then
  TMP="$RUNTIME_ROOT/.post-e3-$SOURCE_COMMIT-$$"
  rm -rf "$TMP"
  mkdir -p "$TMP" "$RUNTIME_ROOT"
  git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$TMP"
  mv "$TMP" "$TARGET"
fi

cd "$TARGET"
echo "agentos_post_e3_source_commit=$SOURCE_COMMIT"
echo "agentos_post_e3_runtime_source=$TARGET"
echo "agentos_post_e3_execution_cwd=$PWD"

echo "agentos_post_e3_contract_tests=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 -m unittest \
    tests.test_project_continuation_index \
    tests.test_canonical_ir_handoff \
    tests.test_active_continuation \
    tests.test_codex_one_mcp_stdio \
    tests.test_install_codex_one_oracle \
    -v
echo "agentos_post_e3_contract_tests=PASS"

echo "agentos_post_e3_canonical_handoff=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/advance_issue_152_after_e3_verified.py"
echo "agentos_post_e3_canonical_handoff=PASS"

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 - <<'PY'
import json
import os
from agent_core.active_continuation import resolve_active_continuation
from agent_core.resolve_facade import resolve_continuation

expected_index = "idx-core-152-post-e3-1"
expected_ir = "ir-core-152-post-e3-1"
state = resolve_continuation("agentos-core", data_root=os.environ["AGENT_DATA_ROOT"])
continuation = state.get("continuation") or {}
ir = continuation.get("canonical_ir") or {}
head = state.get("execution_head") or {}
active = resolve_active_continuation(data_root=os.environ["AGENT_DATA_ROOT"])
selector = active.get("selector") or {}
if str(head.get("index_id") or "") != expected_index:
    raise SystemExit(f"post-E3 execution-head mismatch: {head}")
if str(ir.get("ir_id") or "") != expected_ir or str(ir.get("parent_ir_id") or "") != "ir-core-152-e3-codex-ext-1":
    raise SystemExit(f"post-E3 IR mismatch: {ir}")
if selector.get("index_id") != expected_index or selector.get("ir_id") != expected_ir:
    raise SystemExit(f"post-E3 active selector mismatch: {selector}")
print(json.dumps({
    "schema": "agentos.issue-152-post-e3-probe/v1",
    "ok": True,
    "project_id": "agentos-core",
    "index_id": expected_index,
    "ir_id": expected_ir,
    "parent_ir_id": ir.get("parent_ir_id"),
    "goal": ir.get("goal"),
    "next_action": state.get("next_action"),
    "active_selector": selector,
    "credential_exposed": False,
}, ensure_ascii=False, indent=2, sort_keys=True))
PY

echo "agentos_issue_152_post_e3=PASS"
echo "agentos_post_e3_index_id=$EXPECTED_INDEX"
echo "agentos_post_e3_ir_id=$EXPECTED_IR"

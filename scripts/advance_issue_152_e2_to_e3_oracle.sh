#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: #152 E2->E3 advancement must run as ubuntu on Oracle" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
RUNTIME_ROOT="${AGENTOS_ONE_MCP_SOURCE_ROOT:-/home/ubuntu/.local/share/agentos/one-mcp-source}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
EXPECTED_INDEX="idx-core-152-e3-1"
EXPECTED_IR="ir-core-152-e3-1"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }
test -f "$DATA_ROOT/realm/nodes.json" || { echo "ERROR: Oracle ONE Node Registry missing" >&2; exit 4; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"
TARGET="$RUNTIME_ROOT/$SOURCE_COMMIT"

if [ ! -f "$TARGET/agent_core/canonical_ir_handoff.py" ]; then
  TMP="$RUNTIME_ROOT/.advance-$SOURCE_COMMIT-$$"
  rm -rf "$TMP"
  mkdir -p "$TMP" "$RUNTIME_ROOT"
  git -C "$REPO" archive "$SOURCE_COMMIT" | tar -x -C "$TMP"
  mv "$TMP" "$TARGET"
fi

echo "agentos_e3_source_commit=$SOURCE_COMMIT"
echo "agentos_e3_runtime_source=$TARGET"

echo "agentos_e3_contract_tests=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 -m unittest \
    tests.test_project_continuation_index \
    tests.test_canonical_ir_handoff \
    tests.test_antigravity_one_hook \
    tests.test_one_mcp_stdio_identity \
    -v

echo "agentos_e3_contract_tests=PASS"

# Install the exact same immutable runtime snapshot into Antigravity global
# hook/MCP configuration before advancing the live IR.  The installer probes
# against the still-current E2 parent, so any runtime/config regression fails
# before canonical mutation.
echo "agentos_e3_antigravity_runtime_install=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/install_antigravity_one_mcp_oracle.py"
echo "agentos_e3_antigravity_runtime_install=PASS"

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/advance_issue_152_e2_to_e3.py"

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 - <<'PY'
import json
import os
from agent_core.resolve_facade import resolve_continuation

expected_index = "idx-core-152-e3-1"
expected_ir = "ir-core-152-e3-1"
state = resolve_continuation("agentos-core", data_root=os.environ["AGENT_DATA_ROOT"])
head = state.get("execution_head") or {}
continuation = state.get("continuation") or {}
ir = continuation.get("canonical_ir") or {}
actual_index = str(head.get("index_id") or "")
actual_ir = str(ir.get("ir_id") or "")
if actual_index != expected_index or actual_ir != expected_ir:
    raise SystemExit(
        "E3 child verification failed: "
        f"expected {expected_index}/{expected_ir}, found {actual_index}/{actual_ir}"
    )
print(json.dumps({
    "schema": "agentos.issue-152-e3-child-probe/v1",
    "ok": True,
    "source": "ONE_CANONICAL_IR",
    "project_id": "agentos-core",
    "index_id": actual_index,
    "ir_id": actual_ir,
    "parent_ir_id": ir.get("parent_ir_id"),
    "goal": ir.get("goal"),
    "next_action": state.get("next_action"),
    "credential_exposed": False,
}, ensure_ascii=False, indent=2, sort_keys=True))
PY

echo "agentos_issue_152_e2_to_e3=PASS"
echo "agentos_e3_index_id=$EXPECTED_INDEX"
echo "agentos_e3_ir_id=$EXPECTED_IR"
echo "antigravity_reload_required=YES"

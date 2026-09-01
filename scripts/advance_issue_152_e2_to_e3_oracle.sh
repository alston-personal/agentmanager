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
    tests.test_active_continuation \
    tests.test_antigravity_one_hook \
    tests.test_one_mcp_stdio_identity \
    -v
echo "agentos_e3_contract_tests=PASS"

# The active selector is a pointer only.  Seed it from the current canonical
# generation when absent; if an existing selector is stale, fail closed rather
# than silently moving it.
echo "agentos_e3_active_selector=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/seed_active_continuation.py"
echo "agentos_e3_active_selector=PASS"

# Install the same immutable runtime snapshot.  The self-probe deliberately uses
# /home/ubuntu/acas as workspace and must still hydrate the ONE-selected IR.
echo "agentos_e3_antigravity_runtime_install=RUNNING"
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/install_antigravity_one_mcp_oracle.py"
echo "agentos_e3_antigravity_runtime_install=PASS"

# Idempotent: if E3 is already the canonical generation, this only reconciles
# the active selector to the E3 child and does not republish the IR.
PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 "$TARGET/scripts/advance_issue_152_e2_to_e3.py"

PYTHONPATH="$TARGET" AGENT_DATA_ROOT="$DATA_ROOT" \
  python3 - <<'PY'
import json
import os
from agent_core.active_continuation import resolve_active_continuation
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
active = resolve_active_continuation(data_root=os.environ["AGENT_DATA_ROOT"])
selector = active["selector"]
if (
    selector.get("project_id") != "agentos-core"
    or selector.get("index_id") != expected_index
    or selector.get("ir_id") != expected_ir
):
    raise SystemExit(f"E3 active selector verification failed: {selector}")
print(json.dumps({
    "schema": "agentos.issue-152-e3-child-probe/v2",
    "ok": True,
    "source": "ONE_CANONICAL_IR",
    "selection_source": "ONE_ACTIVE_CONTINUATION",
    "project_id": "agentos-core",
    "index_id": actual_index,
    "ir_id": actual_ir,
    "parent_ir_id": ir.get("parent_ir_id"),
    "goal": ir.get("goal"),
    "next_action": state.get("next_action"),
    "active_selector": selector,
    "credential_exposed": False,
}, ensure_ascii=False, indent=2, sort_keys=True))
PY

echo "agentos_issue_152_e2_to_e3=PASS"
echo "agentos_e3_index_id=$EXPECTED_INDEX"
echo "agentos_e3_ir_id=$EXPECTED_IR"
echo "antigravity_reload_required=YES"

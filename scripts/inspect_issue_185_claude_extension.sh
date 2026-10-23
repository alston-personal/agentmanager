#!/usr/bin/env bash
set -euo pipefail

RECEIPT_PATH="${AGENTOS_CLAUDE_ONE_RECEIPT_PATH:-/home/ubuntu/agent-data/runtime/claude-extension-one-active-resolve-last.json}"
EXPECTED_PROJECT="agentos-core"
EXPECTED_INDEX="idx-core-185-claude-ext-1"
EXPECTED_IR="ir-core-185-claude-ext-1"

printf 'agentos_claude_e185_receipt_path=%s\n' "$RECEIPT_PATH"

python3 - "$RECEIPT_PATH" "$EXPECTED_PROJECT" "$EXPECTED_INDEX" "$EXPECTED_IR" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_project, expected_index, expected_ir = sys.argv[2:5]

if not path.is_file():
    print(json.dumps({
        "schema": "agentos.issue-185-claude-extension-inspection/v1",
        "ok": False,
        "verdict": "CLAUDE_ONE_RESOLVE_RECEIPT_MISSING",
        "credential_exposed": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(4)

record = json.loads(path.read_text(encoding="utf-8"))
checks = {
    "schema_ok": record.get("schema") == "agentos.claude-extension-one-active-resolve-receipt/v1",
    "surface_ok": record.get("surface") == "anthropic-claude-code-extension",
    "executor_ok": record.get("executor_adapter") == "claude-code-extension-adapter" and record.get("executor_identity_bound") is True,
    "source_ok": record.get("source") == "ONE_ACTIVE_CONTINUATION" and record.get("selection_source") == "ONE_ACTIVE_CONTINUATION",
    "generation_ok": record.get("project_id") == expected_project and record.get("index_id") == expected_index and record.get("ir_id") == expected_ir,
    "credential_ok": record.get("credential_exposed") is False,
    "backend_boundary_ok": (
        (record.get("backend_identity_bound") is False and record.get("backend_identity") == "unknown")
        or (record.get("backend_identity_bound") is True and record.get("backend_identity_source") == "trusted-local-config")
    ),
}
ok = all(checks.values())
out = {
    "schema": "agentos.issue-185-claude-extension-inspection/v1",
    "ok": ok,
    "verdict": "CLAUDE_ONE_ACTIVE_RESOLVE_OBSERVED" if ok else "CLAUDE_ONE_ACTIVE_RESOLVE_MISMATCH",
    "checks": checks,
    "recorded_at": record.get("recorded_at"),
    "runtime_source_commit": record.get("runtime_source_commit"),
    "surface": record.get("surface"),
    "executor_adapter": record.get("executor_adapter"),
    "executor_class": record.get("executor_class"),
    "executor_identity_bound": record.get("executor_identity_bound"),
    "backend_class": record.get("backend_class"),
    "backend_identity": record.get("backend_identity"),
    "backend_identity_bound": record.get("backend_identity_bound"),
    "backend_identity_source": record.get("backend_identity_source"),
    "source": record.get("source"),
    "selection_source": record.get("selection_source"),
    "project_id": record.get("project_id"),
    "index_id": record.get("index_id"),
    "ir_id": record.get("ir_id"),
    "credential_exposed": record.get("credential_exposed"),
}
print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if ok else 5)
PY

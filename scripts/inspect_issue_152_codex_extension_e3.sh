#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
RECEIPT="$DATA_ROOT/runtime/codex-one-active-resolve-last.json"
EXPECTED_INDEX="idx-core-152-e3-codex-ext-1"
EXPECTED_IR="ir-core-152-e3-codex-ext-1"

echo "agentos_codex_e3_receipt_path=$RECEIPT"

if [ ! -f "$RECEIPT" ]; then
  echo '{"schema":"agentos.issue-152-codex-extension-inspection/v1","ok":false,"verdict":"CODEX_ONE_RESOLVE_RECEIPT_MISSING"}'
  exit 3
fi

AGENTOS_CODEX_E3_RECEIPT="$RECEIPT" \
AGENTOS_CODEX_E3_EXPECTED_INDEX="$EXPECTED_INDEX" \
AGENTOS_CODEX_E3_EXPECTED_IR="$EXPECTED_IR" \
python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["AGENTOS_CODEX_E3_RECEIPT"])
if path.is_symlink():
    raise SystemExit("ERROR: Codex ONE receipt may not be a symlink")
record = json.loads(path.read_text(encoding="utf-8"))
expected_index = os.environ["AGENTOS_CODEX_E3_EXPECTED_INDEX"]
expected_ir = os.environ["AGENTOS_CODEX_E3_EXPECTED_IR"]
checks = {
    "schema_ok": record.get("schema") == "agentos.codex-one-active-resolve-receipt/v1",
    "surface_ok": record.get("surface") == "codex-local",
    "executor_ok": record.get("executor_class") == "openai-codex-local" and record.get("executor_identity_bound") is True,
    "source_ok": record.get("source") == "ONE_ACTIVE_CONTINUATION" and record.get("selection_source") == "ONE_ACTIVE_CONTINUATION",
    "generation_ok": record.get("project_id") == "agentos-core" and record.get("index_id") == expected_index and record.get("ir_id") == expected_ir,
    "credential_ok": record.get("credential_exposed") is False,
}
ok = all(checks.values())
print(json.dumps({
    "schema": "agentos.issue-152-codex-extension-inspection/v1",
    "ok": ok,
    "verdict": "CODEX_ONE_ACTIVE_RESOLVE_OBSERVED" if ok else "CODEX_ONE_ACTIVE_RESOLVE_MISMATCH",
    "checks": checks,
    "recorded_at": record.get("recorded_at"),
    "runtime_source_commit": record.get("runtime_source_commit"),
    "surface": record.get("surface"),
    "executor_class": record.get("executor_class"),
    "executor_identity_bound": record.get("executor_identity_bound"),
    "source": record.get("source"),
    "selection_source": record.get("selection_source"),
    "project_id": record.get("project_id"),
    "index_id": record.get("index_id"),
    "ir_id": record.get("ir_id"),
    "credential_exposed": record.get("credential_exposed"),
}, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if ok else 4)
PY

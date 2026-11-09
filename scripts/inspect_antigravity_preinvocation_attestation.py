#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA = "agentos.antigravity-preinvocation-attestation/v1"


def main() -> int:
    root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    path = Path(
        os.environ.get(
            "AGENTOS_PREINVOCATION_AUDIT_PATH",
            str(root / "runtime" / "antigravity-preinvocation-last.json"),
        )
    )
    if path.is_symlink():
        raise SystemExit("ERROR: PreInvocation attestation path may not be a symlink")
    if not path.is_file():
        print(json.dumps({
            "schema": "agentos.antigravity-preinvocation-inspection/v2",
            "ok": False,
            "verdict": "ATTESTATION_MISSING",
            "path": str(path),
            "mismatch_reasons": ["attestation_missing"],
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise SystemExit("ERROR: unsupported PreInvocation attestation schema")

    model_name = str(record.get("model_name") or "")
    installer_probe = "installer-probe" in model_name.casefold()
    hydrated = record.get("outcome") == "hydrated" and record.get("injection_emitted") is True
    expected_index = str(os.environ.get("AGENTOS_EXPECTED_E3_INDEX", "idx-core-152-e3-1"))
    expected_ir = str(os.environ.get("AGENTOS_EXPECTED_E3_IR", "ir-core-152-e3-1"))
    generation_ok = (
        record.get("project_id") == "agentos-core"
        and record.get("index_id") == expected_index
        and record.get("ir_id") == expected_ir
        and record.get("selection_source") == "ONE_ACTIVE_CONTINUATION"
    )
    identity_bound = record.get("executor_identity_bound") is True
    executor_is_codex = record.get("executor_class") == "antigravity-codex"
    identity_ok = executor_is_codex and identity_bound
    credential_ok = record.get("credential_exposed") is False

    mismatch_reasons: list[str] = []
    if not hydrated:
        mismatch_reasons.append("hydration_not_emitted")
    if record.get("project_id") != "agentos-core":
        mismatch_reasons.append("project_id_mismatch")
    if record.get("index_id") != expected_index:
        mismatch_reasons.append("index_id_mismatch")
    if record.get("ir_id") != expected_ir:
        mismatch_reasons.append("ir_id_mismatch")
    if record.get("selection_source") != "ONE_ACTIVE_CONTINUATION":
        mismatch_reasons.append("selection_source_mismatch")
    if not executor_is_codex:
        mismatch_reasons.append("executor_class_not_codex")
    if not identity_bound:
        mismatch_reasons.append("executor_identity_unbound")
    if not credential_ok:
        mismatch_reasons.append("credential_boundary_not_proven")

    if installer_probe:
        verdict = "INSTALLER_PROBE_ONLY"
        ok = False
        rc = 4
    elif record.get("outcome") == "fail-closed":
        verdict = "REAL_PREINVOCATION_FAIL_CLOSED"
        ok = False
        rc = 4
    elif hydrated and generation_ok and credential_ok and identity_bound and not executor_is_codex:
        verdict = "REAL_PREINVOCATION_HYDRATED_WRONG_EXECUTOR"
        ok = False
        rc = 8
    elif hydrated and generation_ok and credential_ok and not identity_bound:
        verdict = "REAL_PREINVOCATION_HYDRATED_IDENTITY_UNBOUND"
        ok = False
        rc = 5
    elif hydrated and not generation_ok:
        verdict = "REAL_PREINVOCATION_HYDRATED_GENERATION_MISMATCH"
        ok = False
        rc = 6
    elif hydrated and generation_ok and identity_ok and credential_ok:
        verdict = "REAL_CODEX_PREINVOCATION_HYDRATED"
        ok = True
        rc = 0
    elif record.get("outcome") == "no-injection":
        verdict = "REAL_PREINVOCATION_NO_INJECTION"
        ok = False
        rc = 7
    else:
        verdict = "REAL_PREINVOCATION_UNEXPECTED"
        ok = False
        rc = 4

    safe = {
        "schema": "agentos.antigravity-preinvocation-inspection/v2",
        "ok": ok,
        "verdict": verdict,
        "mismatch_reasons": mismatch_reasons,
        "checks": {
            "hydrated": hydrated,
            "generation_ok": generation_ok,
            "identity_ok": identity_ok,
            "identity_bound": identity_bound,
            "executor_is_codex": executor_is_codex,
            "credential_ok": credential_ok,
        },
        "recorded_at": record.get("recorded_at"),
        "runtime_source_commit": record.get("runtime_source_commit"),
        "hook_schema": record.get("hook_schema"),
        "outcome": record.get("outcome"),
        "injection_emitted": record.get("injection_emitted"),
        "model_name": record.get("model_name"),
        "executor_class": record.get("executor_class"),
        "executor_identity_bound": record.get("executor_identity_bound"),
        "source": record.get("source"),
        "selection_source": record.get("selection_source"),
        "project_id": record.get("project_id"),
        "index_id": record.get("index_id"),
        "ir_id": record.get("ir_id"),
        "conversation_id_sha256": record.get("conversation_id_sha256"),
        "credential_exposed": record.get("credential_exposed"),
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

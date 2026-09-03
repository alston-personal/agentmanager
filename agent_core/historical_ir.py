"""Immutable Historical IR and non-mutating reconciliation projections.

Historical conversations are evidence sources, never a second active
continuation pointer.  This module deliberately separates source preservation
from the governed decision of whether a historical claim applies to the active
Canonical IR.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any


HISTORICAL_IR_SCHEMA = "agentos.historical-ir/v1"
RECONCILIATION_SCHEMA = "agentos.ir-reconciliation/v1"
CANONICAL_IR_SCHEMA = "agentos.ir/v1"
RELATIONS = {"same_as", "supports", "supersedes", "contradicts"}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def historical_ir_id(project_id: str, conversation_id: str, source_digest: str) -> str:
    project = re.sub(r"[^a-zA-Z0-9._-]", "-", str(project_id))
    conversation = re.sub(r"[^a-zA-Z0-9._-]", "-", str(conversation_id))
    digest = str(source_digest).removeprefix("sha256:")
    if not project or not conversation or len(digest) < 12:
        raise ValueError("historical IR requires project, conversation, and source digest")
    return f"hir.{project}.{conversation}.{digest[:12]}"


def terminal_state(signals: dict[str, Any]) -> str:
    passed = int(signals.get("pass_markers") or 0)
    failed = int(signals.get("fail_markers") or 0)
    completed = int(signals.get("completion_markers") or 0)
    if failed and (passed or completed):
        return "mixed"
    if failed:
        return "failed"
    if passed or completed:
        return "completed"
    return "unknown"


def build_historical_ir(candidate: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal source-preserving IR without copying conversation text."""
    project_id = str(candidate.get("project_id") or "").strip()
    conversation_id = str(candidate.get("conversation_id") or "").strip()
    source_digest = str(candidate.get("source_digest") or "").strip()
    source_files = candidate.get("source_files")
    signals = candidate.get("signals")
    if not project_id or not conversation_id or not source_digest:
        raise ValueError("candidate identity is incomplete")
    if not isinstance(source_files, list) or not all(isinstance(item, str) and item for item in source_files):
        raise ValueError("candidate source_files are required")
    if not isinstance(signals, dict):
        raise ValueError("candidate signals are required")
    for key in ("pass_markers", "fail_markers", "completion_markers", "open_task_markers"):
        if not isinstance(signals.get(key), int) or signals[key] < 0:
            raise ValueError(f"candidate signal {key} must be a non-negative integer")
    outcome = terminal_state(signals)
    ir_id = historical_ir_id(project_id, conversation_id, source_digest)
    return {
        "schema_version": HISTORICAL_IR_SCHEMA,
        "historical_ir_id": ir_id,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "source": {
            "digest": source_digest,
            "approved_summary_files": list(source_files),
            "raw_conversation_copied": False,
        },
        "observations": [{
            "observation_id": "terminal-outcome",
            "kind": "terminal-outcome",
            "value": outcome,
            "signals": dict(signals),
            "authority": "source-observation",
        }],
        "claims": [],
        "reconciliation": {
            "status": "unreconciled",
            "automatic_application": False,
            "relationships": [],
        },
        "credential_exposed": False,
    }


def historical_ir_digest(value: dict[str, Any]) -> str:
    validate_historical_ir(value)
    return "sha256:" + sha256(_canonical_bytes(value)).hexdigest()


def validate_historical_ir(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != HISTORICAL_IR_SCHEMA:
        raise ValueError("unsupported Historical IR schema")
    required = ("historical_ir_id", "project_id", "conversation_id", "source", "observations", "claims", "reconciliation")
    if any(not value.get(key) for key in required if key not in {"claims"}):
        raise ValueError("Historical IR is missing required fields")
    if not isinstance(value["source"], dict) or value["source"].get("raw_conversation_copied") is not False:
        raise ValueError("Historical IR must not copy raw conversation")
    if value.get("credential_exposed") is not False:
        raise ValueError("Historical IR credential boundary failed")
    expected = historical_ir_id(value["project_id"], value["conversation_id"], value["source"].get("digest", ""))
    if value["historical_ir_id"] != expected:
        raise ValueError("Historical IR identity does not match source")
    if not isinstance(value["observations"], list) or not isinstance(value["claims"], list):
        raise ValueError("Historical IR observations and claims must be lists")
    return value


def discover_historical_irs(
    project_id: str,
    *,
    data_root: Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return bounded Historical IR metadata for ONE review, never raw summaries."""
    if not isinstance(limit, int) or limit < 1 or limit > 128:
        raise ValueError("Historical IR discovery limit must be between 1 and 128")
    project_id = str(project_id or "").strip()
    if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
        raise ValueError("invalid Historical IR project_id")
    root = Path(data_root or os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")) / "historical-ir" / project_id
    if root.is_symlink():
        raise ValueError("Historical IR project root may not be a symlink")
    if not root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if len(result) >= limit:
            break
        if path.is_symlink() or not path.is_file():
            continue
        value = validate_historical_ir(json.loads(path.read_text(encoding="utf-8")))
        if value["project_id"] != project_id:
            raise ValueError("Historical IR project path/content mismatch")
        result.append({
            "historical_ir_id": value["historical_ir_id"],
            "project_id": value["project_id"],
            "conversation_id": value["conversation_id"],
            "digest": historical_ir_digest(value),
            "source_digest": value["source"]["digest"],
            "observations": value["observations"],
            "reconciliation_status": value["reconciliation"]["status"],
            "raw_conversation_copied": False,
            "credential_exposed": False,
        })
    return result


def reconcile_historical_irs(
    active_ir: dict[str, Any],
    historical_irs: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a derived, non-mutating reconciliation view.

    Only ``supports`` and ``same_as`` become reviewable context candidates.
    Replacement and conflict relations are deliberately quarantined until a
    separate governed Canonical IR advancement accepts them.
    """
    if not isinstance(active_ir, dict) or active_ir.get("schema_version") != CANONICAL_IR_SCHEMA:
        raise ValueError("active IR must be agentos.ir/v1")
    active_id = str(active_ir.get("ir_id") or "").strip()
    project_id = str(active_ir.get("project_id") or "agentos-core").strip()
    if not active_id:
        raise ValueError("active IR requires ir_id")
    indexed = {item["historical_ir_id"]: validate_historical_ir(item) for item in historical_irs}
    if any(item["project_id"] != project_id for item in indexed.values()):
        raise ValueError("Historical IR project does not match active IR project")
    candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for assertion in assertions:
        if not isinstance(assertion, dict):
            raise ValueError("reconciliation assertion must be an object")
        historical_id = str(assertion.get("historical_ir_id") or "").strip()
        relation = str(assertion.get("relation") or "").strip()
        target = str(assertion.get("target_ir_id") or "").strip()
        subject = str(assertion.get("subject") or "").strip()
        if historical_id not in indexed or relation not in RELATIONS or target != active_id or not subject:
            raise ValueError("invalid reconciliation assertion")
        record = {
            "historical_ir_id": historical_id,
            "historical_ir_digest": historical_ir_digest(indexed[historical_id]),
            "target_ir_id": active_id,
            "relation": relation,
            "subject": subject,
            "automatic_application": False,
        }
        if relation in {"supports", "same_as"}:
            key = (relation, subject)
            if key not in seen:
                candidates.append(record)
                seen.add(key)
        else:
            record["requires_governed_canonical_advance"] = True
            quarantined.append(record)
    return {
        "schema": RECONCILIATION_SCHEMA,
        "project_id": project_id,
        "active_ir_id": active_id,
        "active_ir_mutated": False,
        "context_candidates": candidates,
        "quarantined": quarantined,
        "credential_exposed": False,
    }

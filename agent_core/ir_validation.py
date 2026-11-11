"""Deterministic checks for Core canonical publication; no model or network calls."""
from __future__ import annotations

import hashlib
import json
from typing import Any

RULE_VERSION = "core-continuation/1"
CONTEXT_TYPES = {"context": dict, "artifacts": list, "pruned_paths": list,
                 "tensions": list, "frontier": dict}
SEMANTIC_FIELDS = ("goal", "constraints", "decisions", "pending_tasks", "capability",
                   "continuation", *CONTEXT_TYPES)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def validate_ir_change(candidate: dict, *, parent: dict | None = None,
                       writer: str = "explicit") -> dict:
    """Reject malformed/lossy publication; callers still enforce identity/CAS/authority."""
    errors = []
    if not isinstance(candidate, dict):
        raise ValueError("IR_VALIDATION_FAILED: candidate must be an object")
    if candidate.get("schema_version") != "agentos.ir/v1":
        errors.append("SCHEMA")
    for key in ("index_id", "ir_id", "goal", "capability"):
        if not isinstance(candidate.get(key), str) or not candidate[key].strip():
            errors.append(f"REQUIRED:{key}")
    for key in ("constraints", "decisions", "pending_tasks"):
        value = candidate.get(key)
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            errors.append(f"STRING_LIST:{key}")
    continuation = candidate.get("continuation")
    if not isinstance(continuation, dict) or not any(
        isinstance(continuation.get(k), str) and continuation[k].strip()
        for k in ("next_action", "recommended_action")
    ):
        errors.append("CONTINUATION")
    for key, kind in CONTEXT_TYPES.items():
        if key in candidate and not isinstance(candidate[key], kind):
            errors.append(f"CONTEXT_TYPE:{key}")
    if parent is not None:
        if not isinstance(parent, dict):
            raise ValueError("IR_VALIDATION_FAILED: parent must be an object")
        if candidate.get("parent_ir_id") != parent.get("ir_id"):
            errors.append("PARENT")
        if any(candidate.get(k) == parent.get(k) for k in ("ir_id", "index_id")):
            errors.append("NEW_GENERATION")
        for key in parent:
            if key not in candidate:
                errors.append(f"DROPPED_FIELD:{key}")
        if writer == "ir_stop_sync":
            for key in SEMANTIC_FIELDS:
                if candidate.get(key) != parent.get(key):
                    errors.append(f"AUTOMATIC_SEMANTIC_CHANGE:{key}")
    elif writer == "ir_stop_sync":
        errors.append("AUTOMATIC_BOOTSTRAP")
    if errors:
        raise ValueError("IR_VALIDATION_FAILED: " + ",".join(errors))
    return {"schema": "agentos.ir-validation/v1", "verdict": "PASS",
            "rule_version": RULE_VERSION, "candidate_sha256": _digest(candidate),
            "parent_sha256": _digest(parent) if parent is not None else None,
            "writer": writer, "semantic_relevance": "NOT_EVALUATED"}

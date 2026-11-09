from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.project_continuation_index import INITIAL_PROJECT_ID, publish_project_continuation
from agent_core.resolve_facade import resolve_continuation

HANDOFF_SCHEMA = "agentos.canonical-ir-handoff/v1"
IR_SCHEMA = "agentos.ir/v1"
_SENSITIVE_KEYS = {
    "token",
    "node_token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "claim_secret",
    "client_secret",
}


def _contains_sensitive(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().casefold() in _SENSITIVE_KEYS:
                return True
            if _contains_sensitive(child):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive(child) for child in value)
    return False


def _clean_strings(values: Any, *, field: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    out: list[str] = []
    for raw in values:
        item = str(raw or "").strip()
        if not item:
            continue
        if item not in out:
            out.append(item)
    return out


def _validate_evidence(values: Any) -> list[dict[str, Any]]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("evidence must be a list")
    if len(values) > 16:
        raise ValueError("too many evidence entries")
    out: list[dict[str, Any]] = []
    for raw in values:
        if not isinstance(raw, dict):
            raise ValueError("each evidence entry must be an object")
        if _contains_sensitive(raw):
            raise ValueError("evidence contains a sensitive credential field")
        encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > 8192:
            raise ValueError("evidence entry is too large")
        kind = str(raw.get("kind") or "").strip()
        verdict = str(raw.get("verdict") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        if not kind or not verdict or not summary:
            raise ValueError("evidence requires kind, verdict, and summary")
        out.append(dict(raw))
    return out


def advance_canonical_ir(
    params: dict[str, Any],
    *,
    data_root: str | Path | None = None,
    governance_path: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    allowed = {
        "project_id",
        "expected_index_id",
        "expected_ir_id",
        "new_index_id",
        "new_ir_id",
        "goal",
        "next_action",
        "pending_tasks",
        "decisions_append",
        "evidence",
        "capability",
        "execution_status",
        "execution_metadata",
    }
    unknown = set(params) - allowed
    if unknown:
        raise ValueError(f"unsupported handoff fields: {sorted(unknown)}")

    project_id = str(params.get("project_id") or "").strip()
    if project_id != INITIAL_PROJECT_ID:
        raise ValueError("canonical IR handoff is currently restricted to agentos-core")
    expected_index = str(params.get("expected_index_id") or "").strip()
    expected_ir = str(params.get("expected_ir_id") or "").strip()
    new_index = str(params.get("new_index_id") or "").strip()
    new_ir = str(params.get("new_ir_id") or "").strip()
    goal = str(params.get("goal") or "").strip()
    next_action = str(params.get("next_action") or "").strip()
    if not all((expected_index, expected_ir, new_index, new_ir, goal, next_action)):
        raise ValueError("handoff requires expected/new generation ids, goal, and next_action")
    if expected_index == new_index or expected_ir == new_ir:
        raise ValueError("handoff must create a new canonical generation")

    pending_tasks = _clean_strings(params.get("pending_tasks"), field="pending_tasks")
    decisions_append = _clean_strings(params.get("decisions_append"), field="decisions_append")
    evidence_append = _validate_evidence(params.get("evidence"))
    execution_status = str(params.get("execution_status") or "in_progress").strip()
    execution_metadata = params.get("execution_metadata") or {}
    if not isinstance(execution_metadata, dict):
        raise ValueError("execution_metadata must be an object")
    if _contains_sensitive(execution_metadata):
        raise ValueError("execution_metadata contains a sensitive credential field")

    current = resolve_continuation(
        project_id,
        governance_path=governance_path,
        data_root=data_root,
    )
    execution_head = current.get("execution_head") if isinstance(current.get("execution_head"), dict) else {}
    continuation = current.get("continuation") if isinstance(current.get("continuation"), dict) else {}
    canonical_ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else {}
    current_index = str(execution_head.get("index_id") or "").strip()
    current_ir = str(canonical_ir.get("ir_id") or "").strip()
    if canonical_ir.get("schema_version") != IR_SCHEMA:
        raise ValueError("current canonical IR is unavailable or unsupported")
    if current_index != expected_index or current_ir != expected_ir:
        raise ValueError(
            "stale handoff request before publish: "
            f"expected index={expected_index!r} ir={expected_ir!r}, "
            f"found index={current_index!r} ir={current_ir!r}"
        )

    constraints = _clean_strings(canonical_ir.get("constraints") or [], field="current.constraints")
    decisions = _clean_strings(canonical_ir.get("decisions") or [], field="current.decisions")
    for decision in decisions_append:
        if decision not in decisions:
            decisions.append(decision)
    existing_evidence = canonical_ir.get("evidence") or []
    if not isinstance(existing_evidence, list):
        raise ValueError("current canonical IR evidence must be a list")
    if _contains_sensitive(existing_evidence):
        raise ValueError("current canonical IR evidence contains a sensitive field")
    evidence = [dict(item) for item in existing_evidence if isinstance(item, dict)] + evidence_append

    capability = str(params.get("capability") or canonical_ir.get("capability") or "agentos.one.resolve").strip()
    publish_params = {
        "project_id": project_id,
        "execution_head": {
            "schema": "agentos.execution-head/v1",
            "index_id": new_index,
            "active_goal": goal,
            "execution_head": {
                "status": execution_status,
                **execution_metadata,
            },
        },
        "continuation": {
            "protocol": "ANCP/1.0",
            "index_id": new_index,
            "recommended_action": next_action,
            "canonical_ir": {
                "schema_version": IR_SCHEMA,
                "index_id": new_index,
                "ir_id": new_ir,
                "parent_ir_id": expected_ir,
                "goal": goal,
                "constraints": constraints,
                "decisions": decisions,
                "pending_tasks": pending_tasks,
                "evidence": evidence,
                "continuation": {
                    "recommended_action": next_action,
                    "next_action": next_action,
                },
                "capability": capability,
            },
        },
    }
    receipt = publish_project_continuation(
        publish_params,
        data_root=data_root,
        governance_path=governance_path,
        expected_index_id=expected_index,
        expected_ir_id=expected_ir,
    )
    return {
        "schema": HANDOFF_SCHEMA,
        "ok": True,
        "project_id": project_id,
        "parent": {"index_id": expected_index, "ir_id": expected_ir},
        "child": {"index_id": new_index, "ir_id": new_ir},
        "goal": goal,
        "next_action": next_action,
        "evidence_appended": len(evidence_append),
        "credential_exposed": False,
        "publish_receipt": receipt,
    }

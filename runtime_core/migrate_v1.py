"""Compatibility projection from CanonicalIR v1 into State Kernel v2.

The migration deliberately separates canonical project state from execution
intent and routing policy. It is suitable for shadow migration: v1 may remain
authoritative while the v2 projection is computed and compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .canonical_ir import CanonicalIR
from .state_v2 import ProjectState


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ref(kind: str, value: Any) -> str:
    digest = sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"legacy-{kind}:{digest}"


@dataclass(frozen=True)
class LegacyMigrationProjection:
    state: ProjectState
    records: dict[str, Any]
    execution_intent: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "records": self.records,
            "execution_intent": self.execution_intent,
            "provenance": self.provenance,
        }


def canonical_ir_to_state_v2(ir: CanonicalIR) -> LegacyMigrationProjection:
    records: dict[str, Any] = {}
    decision_refs: list[str] = []
    artifact_refs: list[str] = []
    work_items: dict[str, dict[str, Any]] = {}

    for decision in ir.decisions:
        ref = _ref("decision", decision)
        records[ref] = {"kind": "decision", "value": decision}
        decision_refs.append(ref)

    for artifact in ir.artifacts:
        ref = _ref("artifact", artifact)
        records[ref] = {"kind": "artifact", "value": artifact}
        artifact_refs.append(ref)

    for index, pending in enumerate(ir.pending_tasks):
        ref = _ref("work", {"index": index, "value": pending})
        work_id = "work_" + ref.rsplit(":", 1)[-1][:24]
        if isinstance(pending, dict):
            item = dict(pending)
        else:
            item = {"instruction": str(pending)}
        item.setdefault("status", "ready")
        item.setdefault("source", "canonical-ir-v1.pending_tasks")
        item["legacy_ref"] = ref
        work_items[work_id] = item
        records[ref] = {"kind": "work", "value": pending}

    active_work_id = f"legacy-ir:{ir.ir_id}"
    work_items.setdefault(
        active_work_id,
        {
            "status": "ready",
            "capability": ir.capability,
            "instruction": ir.payload.get("instruction") if isinstance(ir.payload, dict) else None,
            "source": "canonical-ir-v1.execution",
        },
    )

    routing = {}
    if isinstance(ir.context, dict):
        if isinstance(ir.context.get("runtime_policy"), dict):
            routing["runtime_policy"] = dict(ir.context["runtime_policy"])
        if isinstance(ir.context.get("provider_policy"), dict):
            routing["provider_policy"] = dict(ir.context["provider_policy"])

    execution_intent = {
        "work_id": active_work_id,
        "project_id": ir.project_id,
        "base_ir_id": ir.ir_id,
        "capability": ir.capability,
        "payload": dict(ir.payload) if isinstance(ir.payload, dict) else {},
        "routing": routing,
    }

    state = ProjectState(
        project_id=ir.project_id,
        goal=ir.goal,
        constraints=tuple(ir.constraints),
        work_items=work_items,
        decision_refs=tuple(decision_refs),
        artifact_refs=tuple(artifact_refs),
        metadata={
            "migration": {
                "source_schema": ir.schema_version,
                "source_ir_id": ir.ir_id,
                "source_parent_ir_id": ir.parent_ir_id,
                "source_hop_count": ir.hop_count,
            }
        },
    )
    provenance = {
        "source_schema": ir.schema_version,
        "source_ir_id": ir.ir_id,
        "source_digest": ir.digest(),
        "source_created_at": ir.created_at,
    }
    return LegacyMigrationProjection(
        state=state,
        records=records,
        execution_intent=execution_intent,
        provenance=provenance,
    )

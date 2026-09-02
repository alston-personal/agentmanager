from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.spec_steward_acceptance import EXPECTED_AUTHORITY_POLICY, EXPECTED_TRANSPORT
from agentos_node.spec_steward_worker import (
    ASSIGNMENT_ID,
    EMPLOYEE_ID,
    SpecStewardWakeWorker,
    SpecStewardWorkerState,
)


ELIGIBLE_PRECLAIM_DELIVERY_STATES = {"queued", "awaiting_claim"}


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("governed_spec_steward_worker_evidence_invalid")
    return payload


def _same_wake(left: Any, right: Any) -> bool:
    return isinstance(left, dict) and isinstance(right, dict) and left == right


def require_governed_spec_steward_delivery(
    runtime_root: str | Path,
    capsule: dict[str, Any],
) -> dict[str, Any]:
    """Require one exact Core/S4 authority record before Employee claim.

    Node wake persistence proves delivery only. It does not grant worker execution
    authority. This check binds the capsule back to the immutable Supervisor
    reconcile intent and its separate one_direct delivery ledger.
    """
    root = Path(runtime_root).expanduser().resolve()
    wake = capsule.get("wake_intent")
    if not isinstance(wake, dict):
        raise PermissionError("spec_steward_worker_governed_wake_missing")
    if capsule.get("employee_id") != EMPLOYEE_ID or capsule.get("assignment_id") != ASSIGNMENT_ID:
        raise PermissionError("spec_steward_worker_governed_scope_mismatch")

    deliveries = root / "supervisor" / "deliveries"
    intents = root / "supervisor" / "intents"
    if not deliveries.is_dir() or not intents.is_dir():
        raise PermissionError("spec_steward_worker_governed_delivery_missing")

    matches: list[dict[str, Any]] = []
    for path in sorted(deliveries.glob("reconcile_*.json")):
        try:
            delivery = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not delivery or delivery.get("schema") != DELIVERY_STATE_SCHEMA:
            continue
        if delivery.get("status") not in ELIGIBLE_PRECLAIM_DELIVERY_STATES:
            continue
        if delivery.get("employee_id") != EMPLOYEE_ID or delivery.get("assignment_id") != ASSIGNMENT_ID:
            continue
        if delivery.get("wake_id") != capsule.get("wake_id"):
            continue
        if delivery.get("transport") != EXPECTED_TRANSPORT:
            continue
        if delivery.get("authority_policy_id") != EXPECTED_AUTHORITY_POLICY:
            continue
        if delivery.get("capability") != WAKE_CAPABILITY:
            continue
        if delivery.get("dispatch_performed") is not True:
            continue
        if delivery.get("node_id") != capsule.get("node_id"):
            continue
        if delivery.get("presence_id") != capsule.get("presence_id"):
            continue
        if int(delivery.get("presence_generation") or 0) != int(capsule.get("presence_generation") or 0):
            continue
        if not delivery.get("task_id") or not delivery.get("wake_attempt_id"):
            continue

        reconcile_id = str(delivery.get("reconcile_id") or "").strip()
        if not reconcile_id or path.stem != reconcile_id:
            continue
        try:
            record = _read(intents / f"{reconcile_id}.json")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not record or record.get("schema") != INTENT_RECORD_SCHEMA:
            continue
        if record.get("reconcile_id") != reconcile_id or record.get("state") != "planned":
            continue
        if record.get("dispatch_performed") is not False:
            continue
        intent = record.get("intent")
        if not isinstance(intent, dict) or intent.get("schema") != RECONCILE_INTENT_SCHEMA:
            continue
        if intent.get("kind") != "employee_wake":
            continue
        if intent.get("employee_id") != EMPLOYEE_ID or intent.get("assignment_id") != ASSIGNMENT_ID:
            continue
        if intent.get("authority_boundary") != "observe_and_select_only":
            continue
        if any(
            intent.get(key) != "unbound"
            for key in ("node_selection", "executor_selection", "transport_selection", "capability_authority")
        ):
            continue
        if intent.get("credential_exposed") is not False:
            continue
        if not _same_wake(intent.get("wake_intent"), wake):
            continue
        matches.append(delivery)

    if len(matches) != 1:
        raise PermissionError(
            "spec_steward_worker_governed_delivery_ambiguous"
            if len(matches) > 1
            else "spec_steward_worker_governed_delivery_missing"
        )
    return matches[0]


class GovernedSpecStewardWakeWorker:
    """Deployment surface for the bounded O3 worker.

    `SpecStewardWakeWorker` is the lifecycle kernel. Runtime deployments must use
    this wrapper so a locally persisted wake capsule cannot bypass Core/S4
    authority resolution.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.worker = SpecStewardWakeWorker(**kwargs)

    def process_one(self, *, now=None) -> SpecStewardWorkerState | None:
        candidates = self.worker._capsules()  # noqa: SLF001 - same bounded worker package
        if not candidates:
            return None
        _, _, capsule = candidates[0]
        require_governed_spec_steward_delivery(self.worker.runtime_root, capsule)
        return self.worker.process_one(now=now)

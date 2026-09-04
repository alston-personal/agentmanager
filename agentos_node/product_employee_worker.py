from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime

EXPECTED_AUTHORITY_POLICY = "core-supervisor-employee-wake-v1"
EXPECTED_TRANSPORT = "one_direct"
ELIGIBLE_PRECLAIM_DELIVERY_STATES = {"awaiting_claim"}
SUPPORTED_PRODUCT_RUNNERS = {
    "zeus_writer_v1": {
        "employee_id": "zeus-writer",
        "assignment_id": "zeus-writer-continuation-v1",
        "role_ids": {"product.zeus_writer"},
        "skill_ids": {"writing.project.continue"},
    },
    "youtube_ai_manager_scan_v1": {
        "employee_id": "youtube-ai-manager",
        "assignment_id": "youtube-ai-manager-scan-v1",
        "role_ids": {"product.youtube_ai_manager"},
        "skill_ids": {"youtube.optimization.scan"},
    },
}


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("product_employee_worker_evidence_invalid")
    return payload


def _same_wake(left: Any, right: Any) -> bool:
    return isinstance(left, dict) and isinstance(right, dict) and left == right


def _require_runner_scope(runner_kind: str, capsule: dict[str, Any]) -> dict[str, Any]:
    scope = SUPPORTED_PRODUCT_RUNNERS.get(str(runner_kind or "").strip())
    if scope is None:
        raise PermissionError("product_employee_runner_kind_not_allowed")
    wake = capsule.get("wake_intent")
    if not isinstance(wake, dict):
        raise PermissionError("product_employee_worker_wake_missing")
    if capsule.get("employee_id") != scope["employee_id"] or capsule.get("assignment_id") != scope["assignment_id"]:
        raise PermissionError("product_employee_worker_scope_mismatch")
    if set(wake.get("role_ids") or []) != scope["role_ids"]:
        raise PermissionError("product_employee_worker_role_scope_mismatch")
    if set(wake.get("skill_ids") or []) != scope["skill_ids"]:
        raise PermissionError("product_employee_worker_skill_scope_mismatch")
    return scope


def require_governed_product_delivery(
    runtime_root: str | Path,
    runner_kind: str,
    capsule: dict[str, Any],
) -> dict[str, Any]:
    """Bind one product wake to one exact Supervisor/S4 delivery before claim."""
    _require_runner_scope(runner_kind, capsule)
    root = Path(runtime_root).expanduser().resolve()
    wake = capsule.get("wake_intent")
    deliveries = root / "supervisor" / "deliveries"
    intents = root / "supervisor" / "intents"
    if not deliveries.is_dir() or not intents.is_dir():
        raise PermissionError("product_employee_worker_governed_delivery_missing")

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
        if delivery.get("employee_id") != capsule.get("employee_id"):
            continue
        if delivery.get("assignment_id") != capsule.get("assignment_id"):
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
        if intent.get("employee_id") != capsule.get("employee_id"):
            continue
        if intent.get("assignment_id") != capsule.get("assignment_id"):
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
            "product_employee_worker_governed_delivery_ambiguous"
            if len(matches) > 1
            else "product_employee_worker_governed_delivery_missing"
        )
    return matches[0]


@dataclass(slots=True)
class ProductWorkerState:
    status: str
    runner_kind: str
    employee_id: str
    assignment_id: str
    wake_id: str
    presence_generation: int
    lease_generation: int
    thread_head: str
    error_code: str | None = None
    executor_provider: str = "unbound"
    executor_model: str = ""


class GovernedProductEmployeeWorker:
    """No-network product Employee worker used to prove the governed wake/claim boundary.

    v1 intentionally performs only a deterministic dry-run checkpoint. Product repository
    writes, publication, YouTube API reads/writes, credentials, network and arbitrary
    executable selection remain outside this worker's authority.
    """

    def __init__(
        self,
        *,
        runtime_root: str | Path,
        wake_root: str | Path,
        worker_state_root: str | Path,
        node_id: str,
        runner_kind: str,
        lease_seconds: int = 60,
    ) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.wake_root = Path(wake_root).expanduser().resolve()
        self.worker_state_root = Path(worker_state_root).expanduser().resolve()
        self.node_id = str(node_id or "").strip()
        self.runner_kind = str(runner_kind or "").strip()
        self.lease_seconds = int(lease_seconds)
        if self.runner_kind not in SUPPORTED_PRODUCT_RUNNERS:
            raise ValueError("product_employee_runner_kind_not_allowed")
        if not self.node_id:
            raise ValueError("product_employee_node_id_required")

    def _capsules(self) -> list[tuple[Path, dict[str, Any]]]:
        scope = SUPPORTED_PRODUCT_RUNNERS[self.runner_kind]
        root = self.wake_root / scope["employee_id"]
        result: list[tuple[Path, dict[str, Any]]] = []
        if not root.is_dir():
            return result
        for path in sorted(root.glob("*.json")):
            try:
                payload = _read(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not payload or payload.get("node_id") != self.node_id:
                continue
            try:
                _require_runner_scope(self.runner_kind, payload)
            except PermissionError:
                continue
            result.append((path, payload))
        return result

    def process_exact(self, *, wake_id: str, presence_generation: int) -> ProductWorkerState | None:
        wake = str(wake_id or "").strip()
        generation = int(presence_generation)
        matches = [
            item
            for item in self._capsules()
            if str(item[1].get("wake_id") or "") == wake
            and int(item[1].get("presence_generation") or 0) == generation
        ]
        if len(matches) > 1:
            raise RuntimeError("product_employee_worker_exact_wake_ambiguous")
        if not matches:
            return None
        _, capsule = matches[0]
        require_governed_product_delivery(self.runtime_root, self.runner_kind, capsule)

        runtime = EmployeeRuntime(self.runtime_root)
        lifecycle = EmployeeLifecycle(runtime)
        employee_id = str(capsule["employee_id"])
        assignment_id = str(capsule["assignment_id"])
        lease_id = f"product-{self.runner_kind}-{wake}-{generation}"
        lease = lifecycle.claim(
            assignment_id,
            employee_id,
            lease_id,
            lease_seconds=self.lease_seconds,
        )
        expected = int(capsule.get("expected_lease_generation") or 0)
        if lease.generation != expected:
            return ProductWorkerState(
                status="unknown",
                runner_kind=self.runner_kind,
                employee_id=employee_id,
                assignment_id=assignment_id,
                wake_id=wake,
                presence_generation=generation,
                lease_generation=lease.generation,
                thread_head=lease.thread_head,
                error_code="product_employee_worker_lease_generation_mismatch",
            )

        thread_head = f"product-worker:{self.runner_kind}:dry-run:{wake}:p{generation}:l{lease.generation}"
        lease = lifecycle.checkpoint(assignment_id, lease_id, thread_head)
        employee = runtime.get_employee(employee_id)
        return ProductWorkerState(
            status="checkpointed",
            runner_kind=self.runner_kind,
            employee_id=employee_id,
            assignment_id=assignment_id,
            wake_id=wake,
            presence_generation=generation,
            lease_generation=lease.generation,
            thread_head=lease.thread_head,
            executor_provider=employee.executor.provider,
            executor_model=employee.executor.model,
        )

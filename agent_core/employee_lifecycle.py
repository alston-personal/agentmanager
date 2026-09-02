from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_core.employee_runtime import Assignment, EmployeeRuntime
from agent_core.role_runtime import RoleRegistry

LEASE_SCHEMA = "agentos.employee-assignment-lease/v1"
RECEIPT_SCHEMA = "agentos.employee-assignment-receipt/v1"
WORK_PACKET_SCHEMA = "agentos.employee-work-packet/v1"
VALID_FINISH_STATES = {"completed", "blocked", "handoff", "cancelled"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _safe_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError("unsafe_lifecycle_id")
    return value


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("lifecycle_state_invalid")
    return value


@dataclass(slots=True)
class AssignmentLease:
    schema: str
    assignment_id: str
    employee_id: str
    lease_id: str
    generation: int
    status: str
    claimed_at: str
    heartbeat_at: str
    expires_at: str
    thread_head: str = ""
    resume_required: bool = False
    prior_execution_state: str = "known"
    resumed_from_lease_id: str | None = None
    last_checkpoint_at: str | None = None


@dataclass(slots=True)
class AssignmentReceipt:
    schema: str
    assignment_id: str
    employee_id: str
    lease_id: str
    generation: int
    outcome: str
    recorded_at: str
    thread_head: str
    role_ids: list[str] = field(default_factory=list)
    executor_provider: str = "unbound"
    executor_model: str = ""
    result_summary: dict[str, Any] = field(default_factory=dict)
    credential_exposed: bool = False


class EmployeeLifecycle:
    """Durable claim/lease/checkpoint/receipt layer for AgentOS employees.

    This module does not invoke a model or choose a privileged execution carrier. It
    only arbitrates which executor session currently owns an Employee assignment and
    preserves enough durable state for another executor to resume safely.

    If a lease expires without a terminal receipt, the next claimant inherits the
    assignment/thread head but `prior_execution_state` is `unknown`. This prevents a
    crashed executor from being silently interpreted as having performed no side
    effects.
    """

    def __init__(self, runtime: EmployeeRuntime) -> None:
        self.runtime = runtime
        self.root = runtime.root / "lifecycle"
        self.leases_dir = self.root / "leases"
        self.receipts_dir = self.root / "receipts"

    def _lease_path(self, assignment_id: str) -> Path:
        return self.leases_dir / f"{_safe_id(assignment_id)}.json"

    def _receipt_path(self, assignment_id: str, generation: int) -> Path:
        return self.receipts_dir / _safe_id(assignment_id) / f"{generation:06d}.json"

    def get_lease(self, assignment_id: str) -> AssignmentLease | None:
        data = _read_json(self._lease_path(assignment_id))
        if data is None:
            return None
        return AssignmentLease(**data)

    @staticmethod
    def lease_expired(lease: AssignmentLease, *, now: datetime | None = None) -> bool:
        current = now or _utcnow()
        return current >= _parse(lease.expires_at)

    def claim(
        self,
        assignment_id: str,
        employee_id: str,
        lease_id: str,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> AssignmentLease:
        if lease_seconds < 30 or lease_seconds > 3600:
            raise ValueError("lease_seconds_out_of_range")
        assignment_id = _safe_id(assignment_id)
        employee_id = _safe_id(employee_id)
        lease_id = _safe_id(lease_id)
        assignment = self.runtime.get_assignment(assignment_id)
        if assignment.employee_id != employee_id:
            raise PermissionError("assignment_employee_mismatch")
        if assignment.state not in {"pending", "active"}:
            raise RuntimeError("assignment_not_claimable")

        current = now or _utcnow()
        existing = self.get_lease(assignment_id)
        if existing and existing.status == "active" and not self.lease_expired(existing, now=current):
            if existing.employee_id == employee_id and existing.lease_id == lease_id:
                return existing
            raise RuntimeError("assignment_already_leased")

        generation = 1
        resume_required = False
        prior_execution_state = "known"
        resumed_from: str | None = None
        if existing is not None:
            generation = existing.generation + 1
            if existing.status == "active" and self.lease_expired(existing, now=current):
                resume_required = True
                prior_execution_state = "unknown"
                resumed_from = existing.lease_id

        expires = current + timedelta(seconds=lease_seconds)
        lease = AssignmentLease(
            schema=LEASE_SCHEMA,
            assignment_id=assignment_id,
            employee_id=employee_id,
            lease_id=lease_id,
            generation=generation,
            status="active",
            claimed_at=_iso(current),
            heartbeat_at=_iso(current),
            expires_at=_iso(expires),
            thread_head=assignment.thread_head,
            resume_required=resume_required,
            prior_execution_state=prior_execution_state,
            resumed_from_lease_id=resumed_from,
        )
        _atomic_json_write(self._lease_path(assignment_id), asdict(lease))
        if assignment.state == "pending":
            self.runtime.update_assignment(assignment_id, state="active")
        return lease

    def heartbeat(
        self,
        assignment_id: str,
        lease_id: str,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> AssignmentLease:
        if lease_seconds < 30 or lease_seconds > 3600:
            raise ValueError("lease_seconds_out_of_range")
        lease = self._require_current_active(assignment_id, lease_id, now=now)
        current = now or _utcnow()
        lease.heartbeat_at = _iso(current)
        lease.expires_at = _iso(current + timedelta(seconds=lease_seconds))
        _atomic_json_write(self._lease_path(assignment_id), asdict(lease))
        return lease

    def checkpoint(
        self,
        assignment_id: str,
        lease_id: str,
        thread_head: str,
        *,
        now: datetime | None = None,
    ) -> AssignmentLease:
        lease = self._require_current_active(assignment_id, lease_id, now=now)
        current = now or _utcnow()
        head = str(thread_head or "").strip()
        if not head:
            raise ValueError("thread_head_required")
        self.runtime.update_assignment(assignment_id, thread_head=head)
        lease.thread_head = head
        lease.last_checkpoint_at = _iso(current)
        _atomic_json_write(self._lease_path(assignment_id), asdict(lease))
        return lease

    def finish(
        self,
        assignment_id: str,
        lease_id: str,
        *,
        state: str = "completed",
        result_summary: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> AssignmentReceipt:
        if state not in VALID_FINISH_STATES:
            raise ValueError("invalid_finish_state")
        lease = self._require_current_active(assignment_id, lease_id, now=now)
        current = now or _utcnow()
        assignment = self.runtime.get_assignment(assignment_id)
        employee = self.runtime.get_employee(assignment.employee_id)
        summary = dict(result_summary or {})
        receipt = AssignmentReceipt(
            schema=RECEIPT_SCHEMA,
            assignment_id=assignment.assignment_id,
            employee_id=assignment.employee_id,
            lease_id=lease.lease_id,
            generation=lease.generation,
            outcome=state,
            recorded_at=_iso(current),
            thread_head=assignment.thread_head,
            role_ids=list(employee.role_ids),
            executor_provider=employee.executor.provider,
            executor_model=employee.executor.model,
            result_summary=summary,
            credential_exposed=False,
        )
        receipt_path = self._receipt_path(assignment_id, lease.generation)
        if receipt_path.exists():
            existing = AssignmentReceipt(**(_read_json(receipt_path) or {}))
            if existing.lease_id == lease_id and existing.outcome == state:
                return existing
            raise RuntimeError("terminal_receipt_conflict")

        # Persist terminal evidence before releasing assignment ownership.
        _atomic_json_write(receipt_path, asdict(receipt))
        self.runtime.update_assignment(
            assignment_id,
            state=state,
            result={
                "schema": RECEIPT_SCHEMA,
                "generation": lease.generation,
                "outcome": state,
                "receipt": str(receipt_path.relative_to(self.runtime.root)),
            },
        )
        lease.status = state
        lease.expires_at = _iso(current)
        _atomic_json_write(self._lease_path(assignment_id), asdict(lease))
        return receipt

    def next_assignment(
        self,
        employee_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[Assignment, bool] | None:
        employee_id = _safe_id(employee_id)
        self.runtime.get_employee(employee_id)
        current = now or _utcnow()
        active_resumable: list[Assignment] = []
        pending: list[Assignment] = []
        if not self.runtime.assignments_dir.exists():
            return None
        for path in sorted(self.runtime.assignments_dir.glob("*.json")):
            assignment = self.runtime.get_assignment(path.stem)
            if assignment.employee_id != employee_id:
                continue
            if assignment.state == "active":
                lease = self.get_lease(assignment.assignment_id)
                if lease is None or lease.status != "active" or self.lease_expired(lease, now=current):
                    active_resumable.append(assignment)
            elif assignment.state == "pending":
                pending.append(assignment)
        if active_resumable:
            active_resumable.sort(key=lambda value: (value.created_at, value.assignment_id))
            return active_resumable[0], True
        if pending:
            pending.sort(key=lambda value: (value.created_at, value.assignment_id))
            return pending[0], False
        return None

    def build_work_packet(
        self,
        assignment_id: str,
        lease_id: str,
        role_registry: RoleRegistry,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        lease = self._require_current_active(assignment_id, lease_id, now=now)
        assignment = self.runtime.get_assignment(assignment_id)
        employee = self.runtime.get_employee(assignment.employee_id)
        roles = role_registry.hydrate_employee_roles(employee.role_ids)
        return {
            "schema": WORK_PACKET_SCHEMA,
            "employee": {
                "agent_id": employee.agent_id,
                "display_name": employee.display_name,
                "memory_namespace": employee.memory_namespace,
                "role_ids": list(employee.role_ids),
                "skill_ids": list(employee.skill_ids),
                "executor": {
                    "provider": employee.executor.provider,
                    "model": employee.executor.model,
                },
            },
            "assignment": {
                "assignment_id": assignment.assignment_id,
                "goal": assignment.goal,
                "state": assignment.state,
                "parent_assignment_id": assignment.parent_assignment_id,
                "thread_head": assignment.thread_head,
                "constraints": list(assignment.constraints),
            },
            "lease": {
                "lease_id": lease.lease_id,
                "generation": lease.generation,
                "expires_at": lease.expires_at,
                "resume_required": lease.resume_required,
                "prior_execution_state": lease.prior_execution_state,
            },
            "roles": [asdict(role) for role in roles],
            "credential_exposed": False,
        }

    def _require_current_active(
        self,
        assignment_id: str,
        lease_id: str,
        *,
        now: datetime | None = None,
    ) -> AssignmentLease:
        lease = self.get_lease(assignment_id)
        if lease is None or lease.status != "active":
            raise RuntimeError("active_lease_required")
        if lease.lease_id != _safe_id(lease_id):
            raise PermissionError("lease_mismatch")
        if self.lease_expired(lease, now=now):
            raise RuntimeError("lease_expired")
        return lease

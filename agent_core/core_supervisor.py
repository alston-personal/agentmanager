from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_wake import EmployeeWakeIntent, EmployeeWakePlanner


RECONCILE_INTENT_SCHEMA = "agentos.core-reconcile-intent/v1"
RECONCILE_PLAN_SCHEMA = "agentos.core-reconcile-plan/v1"


@dataclass(frozen=True, slots=True)
class ReconcileIntent:
    """Authority-neutral durable-work progression intent.

    A reconcile intent says which durable Employee assignment needs attention. It
    deliberately does not choose a Node, executor/model/session, transport,
    capability carrier, executable, argv, URL, or credential. A later governed
    delivery layer may resolve those authorities.
    """

    schema: str
    reconcile_id: str
    kind: str
    employee_id: str
    assignment_id: str
    reason: str
    wake_intent: EmployeeWakeIntent
    authority_boundary: str = "observe_and_select_only"
    node_selection: str = "unbound"
    executor_selection: str = "unbound"
    transport_selection: str = "unbound"
    capability_authority: str = "unbound"
    credential_exposed: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["wake_intent"] = self.wake_intent.as_dict()
        return value


@dataclass(frozen=True, slots=True)
class ReconcileSuppression:
    employee_id: str
    assignment_id: str | None
    reason: str


@dataclass(slots=True)
class ReconcilePlan:
    schema: str = RECONCILE_PLAN_SCHEMA
    intents: list[ReconcileIntent] = field(default_factory=list)
    suppressed: list[ReconcileSuppression] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "intents": [intent.as_dict() for intent in self.intents],
            "suppressed": [asdict(item) for item in self.suppressed],
            "errors": [dict(item) for item in self.errors],
        }


class CoreSupervisorReconciler:
    """Pure/bounded reconciliation kernel for persistent Core supervision.

    This class performs observation and selection only. It does not dispatch a
    wake, claim an Employee assignment, execute a capability, interpret GitHub
    Issue prose, or select any carrier. The future persistent service can call
    this kernel repeatedly and persist/dispatch returned intents through separate
    governed components.
    """

    def __init__(self, lifecycle: EmployeeLifecycle) -> None:
        self.lifecycle = lifecycle
        self.wake_planner = EmployeeWakePlanner(lifecycle)

    @staticmethod
    def _reconcile_id(wake: EmployeeWakeIntent) -> str:
        source = (
            f"{wake.wake_id}\0{wake.employee_id}\0{wake.assignment_id}\0"
            f"{wake.mode}\0{wake.expected_lease_generation}"
        ).encode("utf-8")
        return "reconcile_" + hashlib.sha256(source).hexdigest()[:24]

    def discover_employee_ids(self) -> list[str]:
        directory = self.lifecycle.runtime.employees_dir
        if not directory.exists():
            return []
        return sorted(path.stem for path in directory.glob("*.json") if path.is_file())

    def reconcile(
        self,
        *,
        employee_ids: Iterable[str] | None = None,
        blocked_assignment_ids: Iterable[str] = (),
        persisted_reconcile_ids: Iterable[str] = (),
        now: datetime | None = None,
    ) -> ReconcilePlan:
        blocked = {str(value) for value in blocked_assignment_ids}
        persisted = {str(value) for value in persisted_reconcile_ids}
        selected_employees = sorted(set(employee_ids or self.discover_employee_ids()))
        plan = ReconcilePlan()

        for employee_id in selected_employees:
            try:
                wake = self.wake_planner.plan_next(employee_id, now=now)
            except Exception as exc:  # malformed/unknown state must not create work
                plan.errors.append(
                    {
                        "employee_id": str(employee_id),
                        "error": type(exc).__name__,
                        "disposition": "fail_closed_no_intent",
                    }
                )
                continue

            if wake is None:
                plan.suppressed.append(
                    ReconcileSuppression(
                        employee_id=str(employee_id),
                        assignment_id=None,
                        reason="no_runnable_assignment",
                    )
                )
                continue

            if wake.assignment_id in blocked:
                plan.suppressed.append(
                    ReconcileSuppression(
                        employee_id=wake.employee_id,
                        assignment_id=wake.assignment_id,
                        reason="dependencies_blocked",
                    )
                )
                continue

            reconcile_id = self._reconcile_id(wake)
            if reconcile_id in persisted:
                plan.suppressed.append(
                    ReconcileSuppression(
                        employee_id=wake.employee_id,
                        assignment_id=wake.assignment_id,
                        reason="reconcile_intent_already_persisted",
                    )
                )
                continue

            reason = "assignment_resume_required" if wake.resume_required else "assignment_pending"
            plan.intents.append(
                ReconcileIntent(
                    schema=RECONCILE_INTENT_SCHEMA,
                    reconcile_id=reconcile_id,
                    kind="employee_wake",
                    employee_id=wake.employee_id,
                    assignment_id=wake.assignment_id,
                    reason=reason,
                    wake_intent=wake,
                )
            )

        plan.intents.sort(key=lambda item: (item.employee_id, item.assignment_id, item.reconcile_id))
        plan.suppressed.sort(key=lambda item: (item.employee_id, item.assignment_id or "", item.reason))
        plan.errors.sort(key=lambda item: (item.get("employee_id", ""), item.get("error", "")))
        return plan

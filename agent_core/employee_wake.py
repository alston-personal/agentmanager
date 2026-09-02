from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from agent_core.employee_lifecycle import EmployeeLifecycle


WAKE_INTENT_SCHEMA = "agentos.employee-wake-intent/v1"


@dataclass(frozen=True, slots=True)
class EmployeeWakeIntent:
    """A deterministic request to *consider* waking one employee assignment.

    This is deliberately not an execution request.  It carries no transport,
    Node, provider/model, capability invocation, argv, URL, or credential.  A
    separate governed dispatcher must resolve those authorities after this
    planner has selected the durable Employee assignment that needs attention.
    """

    schema: str
    wake_id: str
    employee_id: str
    assignment_id: str
    mode: str
    expected_lease_generation: int
    goal: str
    thread_head: str
    constraints: tuple[str, ...]
    role_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    resume_required: bool
    prior_execution_state: str
    authority_boundary: str = "selection_only_no_execution"
    executor_selection: str = "unbound"
    transport_selection: str = "unbound"
    credential_exposed: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["constraints"] = list(self.constraints)
        value["role_ids"] = list(self.role_ids)
        value["skill_ids"] = list(self.skill_ids)
        return value


class EmployeeWakePlanner:
    """Read-only planner for durable Employee work that needs a wakeup.

    Selection authority stops at the assignment boundary.  The planner never
    claims a lease and never chooses an executor, Node, transport, or capability.
    Repeated planning before a claim is intentionally idempotent: the same
    assignment/generation produces the same wake_id.
    """

    def __init__(self, lifecycle: EmployeeLifecycle) -> None:
        self.lifecycle = lifecycle

    @staticmethod
    def _wake_id(
        employee_id: str,
        assignment_id: str,
        expected_generation: int,
        mode: str,
    ) -> str:
        source = (
            f"{employee_id}\0{assignment_id}\0{expected_generation}\0{mode}"
        ).encode("utf-8")
        return "wake_" + hashlib.sha256(source).hexdigest()[:24]

    def plan_next(
        self,
        employee_id: str,
        *,
        now: datetime | None = None,
    ) -> EmployeeWakeIntent | None:
        selected = self.lifecycle.next_assignment(employee_id, now=now)
        if selected is None:
            return None

        assignment, resume_required = selected
        employee = self.lifecycle.runtime.get_employee(employee_id)
        lease = self.lifecycle.get_lease(assignment.assignment_id)

        if resume_required:
            # next_assignment() only returns active work as resumable when the
            # previous ownership is absent/terminal/expired.  Any previous live
            # external execution is therefore UNKNOWN until independently
            # verified; the wake planner must not silently downgrade that state.
            mode = "resume"
            prior_execution_state = "unknown"
            expected_generation = (lease.generation + 1) if lease else 1
        else:
            mode = "fresh"
            prior_execution_state = "known"
            expected_generation = (lease.generation + 1) if lease else 1

        return EmployeeWakeIntent(
            schema=WAKE_INTENT_SCHEMA,
            wake_id=self._wake_id(
                employee.agent_id,
                assignment.assignment_id,
                expected_generation,
                mode,
            ),
            employee_id=employee.agent_id,
            assignment_id=assignment.assignment_id,
            mode=mode,
            expected_lease_generation=expected_generation,
            goal=assignment.goal,
            thread_head=assignment.thread_head,
            constraints=tuple(assignment.constraints),
            role_ids=tuple(employee.role_ids),
            skill_ids=tuple(employee.skill_ids),
            resume_required=resume_required,
            prior_execution_state=prior_execution_state,
        )

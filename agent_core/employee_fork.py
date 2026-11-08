"""Bounded Base Role Employee Fork atop existing lifecycle/thread services.

This is an identity/assignment fork, NOT a model process, scheduler or privilege grant.
Experience return is a candidate; ONE alone may accept canonical Experience.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_threads import EmployeeThreadService, ThreadLink
from agent_core.role_runtime import RoleRegistry


@dataclass(frozen=True, slots=True)
class ForkReturnCandidate:
    schema: str
    parent_employee_id: str
    child_employee_id: str
    parent_assignment_id: str
    child_assignment_id: str
    child_outcome: str
    child_receipt_generation: int
    return_id: str
    parent_thread_head_at_spawn: str
    child_thread_head: str
    experience_promotion_status: str = "PENDING_ONE_REVIEW"
    credential_exposed: bool = False


class EmployeeForkService:
    """Child has distinct identity, executor binding and private memory namespace.

    Roles selected for the child must be a nonempty subset of parent's declared
    roles. This conservative rule cannot grant an additional role or capability;
    runtime-level capability authorization remains separate and mandatory.
    """

    def __init__(self, lifecycle: EmployeeLifecycle, role_registry: RoleRegistry):
        self.lifecycle = lifecycle
        self.runtime: EmployeeRuntime = lifecycle.runtime
        self.threads = EmployeeThreadService(lifecycle)
        self.role_registry = role_registry

    def fork(
        self,
        *,
        parent_assignment_id: str,
        parent_lease_id: str,
        child_employee_id: str,
        child_assignment_id: str,
        goal: str,
        role_ids: list[str],
        constraints: list[str] | None = None,
        now: datetime | None = None,
    ) -> ThreadLink:
        if not goal.strip():
            raise ValueError("fork_goal_required")
        parent = self.runtime.get_assignment(parent_assignment_id)
        parent_employee = self.runtime.get_employee(parent.employee_id)
        parent_roles = set(parent_employee.role_ids)
        selected = list(dict.fromkeys(role_ids))
        if not selected or not set(selected).issubset(parent_roles):
            raise PermissionError("fork_role_must_be_parent_subset")
        # Invalid, proposed, cyclic roles are never silently admitted.
        self.role_registry.hydrate_employee_roles(selected)
        self.role_registry.hydrate_employee_roles(list(parent_employee.role_ids))
        # Verify the parent's live lease before making a child identity.
        self.lifecycle._require_current_active(  # noqa: SLF001
            parent_assignment_id, parent_lease_id, now=now
        )
        # Fail on existing child identity/assignment; do not hijack a prior child.
        try:
            self.runtime.get_employee(child_employee_id)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("fork_child_employee_already_exists")
        try:
            self.runtime.get_assignment(child_assignment_id)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("fork_child_assignment_already_exists")

        self.runtime.create_employee(
            child_employee_id,
            child_employee_id,
            role_ids=selected,
            # No skills copied implicitly; explicit capability routing is required.
            skill_ids=[],
        )
        return self.threads.spawn_child(
            parent_assignment_id,
            parent_lease_id,
            child_assignment_id,
            child_employee_id,
            goal,
            constraints=[*(constraints or []), "no_implicit_privilege_escalation",
                         "no_automatic_parent_private_memory_copy"],
            now=now,
        )

    def prepare_experience_return(
        self, child_assignment_id: str, *, now: datetime | None = None
    ) -> ForkReturnCandidate:
        """Require a terminal lifecycle receipt, expose only bounded linkage.

        Do not read/copy private memory or accept Experience into ONE here.
        Non-completed child outcomes are not positive learning evidence.
        """
        envelope = self.threads.prepare_return(child_assignment_id, now=now)
        if envelope.child_outcome != "completed":
            raise RuntimeError("fork_not_completed_no_positive_experience")
        return ForkReturnCandidate(
            schema="agentos.employee-fork-experience-candidate/v1",
            parent_employee_id=envelope.parent_employee_id,
            child_employee_id=envelope.child_employee_id,
            parent_assignment_id=envelope.parent_assignment_id,
            child_assignment_id=envelope.child_assignment_id,
            child_outcome=envelope.child_outcome,
            child_receipt_generation=envelope.child_receipt_generation,
            return_id=envelope.return_id,
            parent_thread_head_at_spawn=envelope.parent_thread_head_at_spawn,
            child_thread_head=envelope.child_thread_head,
        )

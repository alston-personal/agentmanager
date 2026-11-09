"""Read-only trusted-Issuer eligibility probe for an exact Paw lease.

This is deliberately not an issuer daemon. It does not sign, dispatch, claim,
alter ledger state, or authorize work from a wake capsule.
"""
from __future__ import annotations

from pathlib import Path
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_lifecycle import EmployeeLifecycle
from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def inspect_trusted_paw_lease(runtime_root: Path, assignment_id: str, lease_id: str) -> dict:
    runtime = EmployeeRuntime(runtime_root)
    lifecycle = EmployeeLifecycle(runtime)
    require_dynamic_paw_assignment_binding(assignment_id=assignment_id, runtime=runtime)
    lease = lifecycle.get_lease(assignment_id)
    if (
        lease is None or lease.assignment_id != assignment_id
        or lease.employee_id != "the-paw" or lease.lease_id != lease_id
        or lease.status != "active" or lease.resume_required
        or lease.prior_execution_state != "known"
        or lifecycle.lease_expired(lease)
    ):
        raise PawWorktreeBoundaryError("paw_issuer_live_lease_not_authorized")
    return {
        "assignment_id": assignment_id,
        "lease_id": lease_id,
        "lease_generation": lease.generation,
        "status": "eligible_for_separate_issuer_review",
        "authorized_to_sign": False,
    }

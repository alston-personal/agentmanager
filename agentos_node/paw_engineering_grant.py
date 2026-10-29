"""Fail-closed Paw engineering execution grant contract (validation only).

A grant must originate in a separately trusted control plane. This module does
not issue grants, invoke models, change employee privileges or execute patches.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError, REPOSITORY, _SHA, _ID

SCHEMA = "agentos.paw-engineering-grant/v1"
_ACTION = "prepare-static-test-candidate"
_SCOPE = "tests/test_paw_engineering_worktree.py"


@dataclass(frozen=True)
class PawEngineeringGrant:
    work_id: str
    assignment_id: str
    wake_id: str
    presence_generation: int
    lease_generation: int
    repository_id: str
    base_sha: str
    allowed_path: str
    action: str


def validate_paw_engineering_grant(
    payload: Mapping[str, object], *,
    expected_assignment_id: str,
    expected_wake_id: str,
    expected_presence_generation: int,
    expected_lease_generation: int,
    allow_dynamic_assignment: bool = False,
) -> PawEngineeringGrant:
    """Compare all authoritative values to the existing governed wake/lease.

    Passing is a *necessary*, never sufficient authorization condition:
    caller must independently authenticate the trusted grant issuer.
    """
    if not isinstance(payload, dict) or set(payload) != {
        "schema", "work_id", "assignment_id", "wake_id",
        "presence_generation", "lease_generation", "repository_id",
        "base_sha", "allowed_path", "action",
    }:
        raise PawWorktreeBoundaryError("paw_grant_shape_invalid")
    if payload["schema"] != SCHEMA or payload["repository_id"] != REPOSITORY:
        raise PawWorktreeBoundaryError("paw_grant_scope_invalid")
    if payload["allowed_path"] != _SCOPE or payload["action"] != _ACTION:
        raise PawWorktreeBoundaryError("paw_grant_action_not_authorized")
    work_id = payload["work_id"]
    if not isinstance(work_id, str) or not _ID.fullmatch(work_id):
        raise PawWorktreeBoundaryError("paw_grant_work_id_invalid")
    sha = payload["base_sha"]
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise PawWorktreeBoundaryError("paw_grant_base_invalid")
    if payload["assignment_id"] != expected_assignment_id or payload["wake_id"] != expected_wake_id:
        raise PawWorktreeBoundaryError("paw_grant_wake_mismatch")
    pg, lg = payload["presence_generation"], payload["lease_generation"]
    if (
        type(pg) is not int or type(lg) is not int or pg < 1 or lg < 1
        or pg != expected_presence_generation or lg != expected_lease_generation
    ):
        raise PawWorktreeBoundaryError("paw_grant_lease_mismatch")
    if (not isinstance(expected_assignment_id, str)
            or not _ID.fullmatch(expected_assignment_id)
            or (expected_assignment_id != "paw-470-inspection-v1" and allow_dynamic_assignment is not True)):
        raise PawWorktreeBoundaryError("paw_grant_assignment_invalid")
    if not isinstance(expected_wake_id, str) or not re.fullmatch(r"wake_[a-f0-9]{24}", expected_wake_id):
        raise PawWorktreeBoundaryError("paw_grant_wake_invalid")
    return PawEngineeringGrant(
        work_id=work_id, assignment_id=expected_assignment_id,
        wake_id=expected_wake_id, presence_generation=pg, lease_generation=lg,
        repository_id=REPOSITORY, base_sha=sha, allowed_path=_SCOPE, action=_ACTION,
    )


def require_canonical_paw_authority(
    grant: PawEngineeringGrant, *,
    registry_path: str | "Path",
    source_ref: str = "core/integration",
    runtime: object | None = None,
) -> None:
    """Require the existing canonical authority resolver, not the wake transport.

    This checks policy admission only. An authenticated issuer, live ONE lease,
    sandbox and independent acceptance remain separate mandatory gates.
    """
    import json
    from pathlib import Path
    from agent_core.governed_execution import (
        REQUEST_SCHEMA, RECEIPT_SCHEMA, resolve_authority,
    )

    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    request = {
        "schema": REQUEST_SCHEMA,
        "request_id": "paw-470-" + grant.work_id,
        "project_id": "agentos-core",
        "repository": grant.repository_id,
        "source_ref": source_ref,
        "source_sha": grant.base_sha,
        "capability": "paw.engineering.candidate.prepare",
        "environment": "isolated-worktree",
        "parameters": {
            "work_id": grant.work_id,
            "wake_id": grant.wake_id,
            "presence_generation": grant.presence_generation,
            "lease_generation": grant.lease_generation,
            "allowed_path": grant.allowed_path,
            "action": grant.action,
        },
        "replay_policy": "idempotent",
        "expected_result": RECEIPT_SCHEMA,
    }
    project, capability = resolve_authority(request, registry)
    canonical_assignment = project.get("employee_binding") == {
        "employee_id": "the-paw", "assignment_id": grant.assignment_id,
    }
    if not canonical_assignment:
        if runtime is None:
            raise PawWorktreeBoundaryError("paw_dynamic_binding_missing")
        require_dynamic_paw_assignment_binding(assignment_id=grant.assignment_id, runtime=runtime)
        if project.get("employee_binding", {}).get("employee_id") != "the-paw":
            raise PawWorktreeBoundaryError("paw_canonical_authority_boundary_invalid")
    if (
        capability.get("adapter") != "paw_engineering_candidate"
        or capability.get("runtime") != {
            "mutation_scope": "isolated-worktree-only",
            "merge_allowed": False,
            "deploy_allowed": False,
            "ledger_done_allowed": False,
            "independent_claw_required": True,
        }
    ):
        raise PawWorktreeBoundaryError("paw_canonical_authority_boundary_invalid")


def require_dynamic_paw_assignment_binding(
    *, assignment_id: str, runtime: object, work_item_id: str | None = None,
    terminal_publication: bool = False,
) -> None:
    """Read-only binding check; terminal publication never grants execution."""
    from agent_core.core_work_items import WorkItemStore
    if not assignment_id:
        raise PawWorktreeBoundaryError("paw_dynamic_binding_missing")
    try:
        assignment = runtime.get_assignment(assignment_id)
        employee = runtime.get_employee("the-paw")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PawWorktreeBoundaryError("paw_dynamic_binding_not_authorized") from exc
    # A trusted caller must not choose one favorable WorkItem among duplicate
    # claims for the same Assignment.
    store = WorkItemStore(runtime)
    try:
        matches = [
            store.get(path.stem) for path in store.root.glob("*.json")
            if store.get(path.stem).assignment_id == assignment_id
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PawWorktreeBoundaryError("paw_dynamic_binding_not_authorized") from exc
    if len(matches) != 1 or (work_item_id is not None and matches[0].work_item_id != work_item_id):
        raise PawWorktreeBoundaryError("paw_dynamic_binding_ambiguous")
    item = matches[0]
    if terminal_publication:
        from agent_core.employee_lifecycle import EmployeeLifecycle
        lifecycle = EmployeeLifecycle(runtime)
        lease = lifecycle.get_lease(assignment_id)
        result = assignment.result if isinstance(assignment.result, dict) else {}
        if (lease is None or lease.employee_id != "the-paw"
                or lease.assignment_id != assignment_id or lease.status != "handoff"
                or result.get("schema") != "agentos.employee-assignment-receipt/v1"
                or result.get("generation") != lease.generation
                or result.get("outcome") != "handoff"):
            raise PawWorktreeBoundaryError("paw_terminal_publication_receipt_invalid")
        receipt_path = lifecycle._receipt_path(assignment_id, lease.generation)
        if (receipt_path.is_symlink() or not receipt_path.is_file()
                or result.get("receipt") != str(receipt_path.relative_to(runtime.root))):
            raise PawWorktreeBoundaryError("paw_terminal_publication_receipt_invalid")
        try:
            import json
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise PawWorktreeBoundaryError("paw_terminal_publication_receipt_invalid") from exc
        if (not isinstance(receipt, dict) or receipt.get("schema") != result["schema"]
                or receipt.get("assignment_id") != assignment_id
                or receipt.get("employee_id") != "the-paw"
                or receipt.get("generation") != lease.generation
                or receipt.get("lease_id") != lease.lease_id
                or receipt.get("outcome") != "handoff"):
            raise PawWorktreeBoundaryError("paw_terminal_publication_receipt_invalid")
    if item.dependency_refs:
        from agent_core.core_supervisor_service import CoreSupervisorService
        from agent_core.employee_lifecycle import EmployeeLifecycle
        supervisor = CoreSupervisorService(
            EmployeeLifecycle(runtime), owner_id="paw-binding-readonly"
        )
        if not WorkItemStore(runtime).dependencies_ready(
            item.work_item_id, supervisor._verified_dependency_states()
        ):
            raise PawWorktreeBoundaryError("paw_dynamic_dependency_not_verified")
    if (
        item.assignment_id != assignment_id
        or item.employee_id != "the-paw"
        or item.state != "open"
        or assignment.employee_id != "the-paw"
        or assignment.state not in ({"handoff"} if terminal_publication else {"pending", "active"})
        or "engineering.work.inspect" not in item.required_capabilities
        or "one-governed-dispatch" not in item.authority_requirements
        or "sector.paw" not in employee.role_ids
        or "engineering.work.inspect" not in employee.skill_ids
    ):
        raise PawWorktreeBoundaryError("paw_dynamic_binding_not_authorized")


def require_live_paw_lease(
    grant: PawEngineeringGrant, *,
    lifecycle: object,
    expected_lease_id: str,
) -> None:
    """Require a currently active exact Paw lease before privileged execution.

    Validating a wake capsule alone does not authorize mutation. The trusted
    caller must obtain lifecycle from the canonical Employee Runtime, not from
    untrusted wake input. Repeat this check at each mutation boundary.
    """
    lease = lifecycle.get_lease(grant.assignment_id)
    if (
        lease is None
        or lease.assignment_id != grant.assignment_id
        or lease.employee_id != "the-paw"
        or lease.lease_id != expected_lease_id
        or lease.generation != grant.lease_generation
        or lease.status != "active"
        or lease.resume_required
        or lease.prior_execution_state != "known"
        or lifecycle.lease_expired(lease)
    ):
        raise PawWorktreeBoundaryError("paw_live_lease_not_authorized")

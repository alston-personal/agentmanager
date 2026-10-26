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
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", expected_assignment_id)):
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
    if (
        project.get("employee_binding") != {
            "employee_id": "the-paw",
            "assignment_id": grant.assignment_id,
        }
        or capability.get("adapter") != "paw_engineering_candidate"
        or capability.get("runtime") != {
            "mutation_scope": "isolated-worktree-only",
            "merge_allowed": False,
            "deploy_allowed": False,
            "ledger_done_allowed": False,
            "independent_claw_required": True,
        }
    ):
        raise PawWorktreeBoundaryError("paw_canonical_authority_boundary_invalid")


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

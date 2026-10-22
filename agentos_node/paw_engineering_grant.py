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
    if not isinstance(expected_assignment_id, str) or expected_assignment_id != "paw-470-inspection-v1":
        raise PawWorktreeBoundaryError("paw_grant_assignment_invalid")
    if not isinstance(expected_wake_id, str) or not re.fullmatch(r"wake_[a-f0-9]{24}", expected_wake_id):
        raise PawWorktreeBoundaryError("paw_grant_wake_invalid")
    return PawEngineeringGrant(
        work_id=work_id, assignment_id=expected_assignment_id,
        wake_id=expected_wake_id, presence_generation=pg, lease_generation=lg,
        repository_id=REPOSITORY, base_sha=sha, allowed_path=_SCOPE, action=_ACTION,
    )

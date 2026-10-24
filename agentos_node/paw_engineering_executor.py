"""Trusted-caller entry for bounded Paw engineering candidate and local commit.

This module is not a ONE grant issuer, remote PR publisher or Claw verifier.
It must be invoked by a trusted runtime with an authenticated grant and a
canonical EmployeeLifecycle instance. No untrusted wake input may select paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from agentos_node.paw_engineering_grant import (
    validate_paw_engineering_grant, require_canonical_paw_authority,
    require_live_paw_lease,
)
from agentos_node.paw_engineering_worktree import prepare_paw_worktree
from agentos_node.paw_engineering_candidate import apply_bounded_test_candidate
from agentos_node.paw_engineering_commit import commit_verified_paw_candidate


def run_authorized_static_candidate(
    *,
    grant_payload: Mapping[str, object],
    trusted_wake_id: str,
    trusted_presence_generation: int,
    trusted_lease_generation: int,
    trusted_lease_id: str,
    lifecycle: object,
    registry_path: Path,
    repository: Path,
    workspace_root: Path,
    expected_sha256: str,
    replacement: str,
):
    """Perform only the narrow static test candidate authorized in policy.

    The caller authenticates issuer and supplies trusted wake/lease identity.
    The local git commit remains unpublished and never implies acceptance.
    """
    grant = validate_paw_engineering_grant(
        grant_payload,
        expected_assignment_id="paw-470-inspection-v1",
        expected_wake_id=trusted_wake_id,
        expected_presence_generation=trusted_presence_generation,
        expected_lease_generation=trusted_lease_generation,
    )
    require_canonical_paw_authority(grant, registry_path=registry_path)
    require_live_paw_lease(
        grant, lifecycle=lifecycle, expected_lease_id=trusted_lease_id,
    )
    prepared = prepare_paw_worktree(
        repository=repository, workspace_root=workspace_root,
        work_id=grant.work_id, base_sha=grant.base_sha,
        repository_id=grant.repository_id,
    )
    require_live_paw_lease(
        grant, lifecycle=lifecycle, expected_lease_id=trusted_lease_id,
    )
    candidate = apply_bounded_test_candidate(
        prepared, relative_path=grant.allowed_path,
        expected_sha256=expected_sha256, replacement=replacement,
    )
    require_live_paw_lease(
        grant, lifecycle=lifecycle, expected_lease_id=trusted_lease_id,
    )
    return commit_verified_paw_candidate(
        prepared, candidate, work_id=grant.work_id,
    )

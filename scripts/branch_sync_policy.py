"""Pure decision policy for when an Executor may attempt mainline reconciliation.

Advisory to Supervisor: no Git writes, task dispatch, lease acquisition or
authorization here. Trusted caller must supply observations from the real
worktree/remote and prove ownership of the active lease independently.
"""
from __future__ import annotations

from typing import Literal

Overlap = Literal["none", "shared", "unknown"]
Kind = Literal["code", "read_only"]


def assess_sync_point(
    *,
    kind: Kind,
    mainline_current: bool | None,
    checkpoint_saved: bool,
    lease_fenced: bool,
    worktree_clean: bool,
    overlapping_changes: Overlap,
    governance_or_security_change: bool,
    hours_since_main_sync: int | None,
) -> dict:
    """Classify a safe *candidate* for integration, never perform a merge.

    "Overlapping" means a verified dependency or file/API overlap, not simply
    a nonzero behind count. Age thresholds are advisory initial policy and
    require real timestamps from an authoritative source.
    """
    if kind not in ("code", "read_only"):
        raise ValueError("invalid_kind")
    if overlapping_changes not in ("none", "shared", "unknown"):
        raise ValueError("invalid_overlap")
    if hours_since_main_sync is not None and (
        isinstance(hours_since_main_sync, bool)
        or not isinstance(hours_since_main_sync, int)
        or hours_since_main_sync < 0
    ):
        raise ValueError("invalid_sync_age")
    if mainline_current is not None and type(mainline_current) is not bool:
        raise ValueError("invalid_mainline_observation")
    if any(type(x) is not bool for x in (
        checkpoint_saved, lease_fenced, worktree_clean,
        governance_or_security_change,
    )):
        raise ValueError("invalid_checkpoint_observation")
    if kind == "read_only":
        return _result("READ_ONLY_CONTINUE", "Read-only inspection cannot promote code")
    if mainline_current is None:
        return _result("EVIDENCE_REQUIRED", "Verify remote main and the work commit")
    if mainline_current:
        return _result("CURRENT", "No mainline integration needed")
    # Main has advanced. Determine when to stop *relevant* new writes.
    at_risk = governance_or_security_change or overlapping_changes == "shared"
    overdue = hours_since_main_sync is not None and hours_since_main_sync >= 72
    if not checkpoint_saved or not lease_fenced or not worktree_clean:
        return _result(
            "WAIT_FOR_SAFE_CHECKPOINT",
            "Persist work and fence the lease; never merge into a dirty worktree",
            block_relevant_writes=at_risk or overdue,
        )
    if overlapping_changes == "unknown":
        return _result(
            "REVIEW_DEPENDENCIES",
            "Dependency overlap must be verified before integrating",
            block_relevant_writes=governance_or_security_change or overdue,
        )
    if at_risk:
        return _result(
            "RECONCILE_REQUIRED",
            "Review relevant changes and integrate in an isolated worktree",
            block_relevant_writes=True,
        )
    if overdue:
        return _result(
            "ESCALATE_STALE_BRANCH",
            "Long-lived stale branch requires accountable Supervisor review",
            block_relevant_writes=True,
        )
    return _result(
        "SAFE_SYNC_CANDIDATE",
        "An isolated merge simulation and CI are still required before switching HEAD",
    )


def _result(status: str, reason: str, block_relevant_writes: bool = False) -> dict:
    return {
        "schema": "agentos.branch-sync-decision/v1",
        "status": status,
        "reason": reason,
        "block_relevant_writes": block_relevant_writes,
        "auto_merge_authorized": False,
        "source_mutated": False,
        "receipt_verified": False,
    }

"""Fail-closed canonical anchor resolution for resumed AgentOS execution."""
from __future__ import annotations

from dataclasses import dataclass

from runtime_core.goal_controller import GoalControllerState


class AnchorResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepositoryObservation:
    repository: str
    ref: str
    head_sha: str


@dataclass(frozen=True)
class CanonicalAnchor:
    project_id: str
    goal_id: str
    repository: str
    canonical_ref: str
    head_sha: str
    goal_revision: int
    next_action: str
    reconciled: bool


def resolve_canonical_anchor(
    goal: GoalControllerState,
    *,
    observation: RepositoryObservation,
    allow_head_reconcile: bool = False,
) -> CanonicalAnchor:
    """Resolve execution coordinates from durable goal state, never repo defaults.

    A resuming executor is not allowed to silently substitute `main` (or any other
    default branch) for the goal's canonical ref. HEAD drift also fails closed
    unless the caller explicitly enters reconciliation after an authoritative read.
    """
    if observation.repository != goal.repository:
        raise AnchorResolutionError("CANONICAL_REPOSITORY_MISMATCH")
    if observation.ref != goal.canonical_ref:
        raise AnchorResolutionError("CANONICAL_REF_MISMATCH")
    if not observation.head_sha.strip():
        raise AnchorResolutionError("CANONICAL_HEAD_MISSING")

    if observation.head_sha != goal.observed_head_sha and not allow_head_reconcile:
        raise AnchorResolutionError("CANONICAL_HEAD_DRIFT_REQUIRES_RECONCILIATION")

    return CanonicalAnchor(
        project_id=goal.project_id,
        goal_id=goal.goal_id,
        repository=goal.repository,
        canonical_ref=goal.canonical_ref,
        head_sha=observation.head_sha,
        goal_revision=goal.revision,
        next_action=goal.next_action,
        reconciled=observation.head_sha != goal.observed_head_sha,
    )


def reconcile_canonical_anchor(
    goal: GoalControllerState,
    *,
    observation: RepositoryObservation,
) -> tuple[GoalControllerState, CanonicalAnchor]:
    """Explicitly reconcile an authoritative HEAD observation into durable state."""
    anchor = resolve_canonical_anchor(goal, observation=observation, allow_head_reconcile=True)
    if anchor.reconciled:
        goal = goal.reconcile_head(current_head_sha=anchor.head_sha)
        anchor = CanonicalAnchor(
            project_id=goal.project_id,
            goal_id=goal.goal_id,
            repository=goal.repository,
            canonical_ref=goal.canonical_ref,
            head_sha=goal.observed_head_sha,
            goal_revision=goal.revision,
            next_action=goal.next_action,
            reconciled=True,
        )
    return goal, anchor

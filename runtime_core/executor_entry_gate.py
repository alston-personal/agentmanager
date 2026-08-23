"""Mandatory trusted entry envelope for heterogeneous AgentOS executors."""
from __future__ import annotations

from dataclasses import dataclass

from runtime_core.canonical_anchor import CanonicalAnchor, RepositoryObservation, resolve_canonical_anchor
from runtime_core.goal_controller import GoalControllerState


@dataclass(frozen=True)
class ExecutorEntryEnvelope:
    """Trusted execution coordinates compiled before model-native planning begins."""

    project_id: str
    goal_id: str
    goal_revision: int
    repository: str
    canonical_ref: str
    verified_head_sha: str
    next_action: str
    execution_state: str
    authority_bound: bool = True

    def trusted_context(self) -> dict[str, str | int | bool]:
        return {
            "project_id": self.project_id,
            "goal_id": self.goal_id,
            "goal_revision": self.goal_revision,
            "repository": self.repository,
            "canonical_ref": self.canonical_ref,
            "verified_head_sha": self.verified_head_sha,
            "next_action": self.next_action,
            "execution_state": self.execution_state,
            "authority_bound": self.authority_bound,
        }


def compile_executor_entry(
    goal: GoalControllerState,
    *,
    repository_observation: RepositoryObservation,
) -> ExecutorEntryEnvelope:
    """Gate executor entry on an exact canonical anchor.

    Repository defaults and executor-selected branches are deliberately not inputs.
    If authoritative coordinates do not match durable goal state, planning must not
    begin; callers must reconcile first through the canonical-anchor protocol.
    """
    anchor: CanonicalAnchor = resolve_canonical_anchor(
        goal,
        observation=repository_observation,
        allow_head_reconcile=False,
    )
    return ExecutorEntryEnvelope(
        project_id=anchor.project_id,
        goal_id=anchor.goal_id,
        goal_revision=anchor.goal_revision,
        repository=anchor.repository,
        canonical_ref=anchor.canonical_ref,
        verified_head_sha=anchor.head_sha,
        next_action=anchor.next_action,
        execution_state=goal.execution_state,
    )

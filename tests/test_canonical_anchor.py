import pytest

from runtime_core.canonical_anchor import (
    AnchorResolutionError,
    RepositoryObservation,
    reconcile_canonical_anchor,
    resolve_canonical_anchor,
)
from runtime_core.goal_controller import GoalControllerState


def goal():
    return GoalControllerState(
        goal_id="G-ANCHOR",
        project_id="agentmanager",
        goal="preserve canonical execution state",
        revision=7,
        execution_state="EXECUTING",
        lease_owner="executor",
        lease_epoch=2,
        next_action="run-real-weak-executor-trial",
        capability_manifest_digest="cap",
        execution_environment_fingerprint="executor/v1",
        repository="alston-personal/agentmanager",
        canonical_ref="feature/distributed-agentos-runtime",
        observed_head_sha="working-head",
    )


def test_exact_canonical_anchor_resolves_without_reconciliation():
    anchor = resolve_canonical_anchor(
        goal(),
        observation=RepositoryObservation(
            repository="alston-personal/agentmanager",
            ref="feature/distributed-agentos-runtime",
            head_sha="working-head",
        ),
    )
    assert anchor.canonical_ref == "feature/distributed-agentos-runtime"
    assert anchor.head_sha == "working-head"
    assert anchor.reconciled is False


def test_default_main_cannot_silently_replace_active_working_ref():
    with pytest.raises(AnchorResolutionError, match="CANONICAL_REF_MISMATCH"):
        resolve_canonical_anchor(
            goal(),
            observation=RepositoryObservation(
                repository="alston-personal/agentmanager",
                ref="main",
                head_sha="738ccd2",
            ),
        )


def test_head_drift_fails_closed_until_explicit_reconciliation():
    observation = RepositoryObservation(
        repository="alston-personal/agentmanager",
        ref="feature/distributed-agentos-runtime",
        head_sha="new-head",
    )
    with pytest.raises(AnchorResolutionError, match="CANONICAL_HEAD_DRIFT_REQUIRES_RECONCILIATION"):
        resolve_canonical_anchor(goal(), observation=observation)

    reconciled_goal, anchor = reconcile_canonical_anchor(goal(), observation=observation)
    assert reconciled_goal.observed_head_sha == "new-head"
    assert reconciled_goal.revision == 8
    assert anchor.reconciled is True
    assert anchor.goal_revision == 8


def test_wrong_repository_fails_closed():
    with pytest.raises(AnchorResolutionError, match="CANONICAL_REPOSITORY_MISMATCH"):
        resolve_canonical_anchor(
            goal(),
            observation=RepositoryObservation(
                repository="someone/else",
                ref="feature/distributed-agentos-runtime",
                head_sha="working-head",
            ),
        )

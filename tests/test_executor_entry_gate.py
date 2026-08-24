import pytest

from runtime_core.canonical_anchor import AnchorResolutionError, RepositoryObservation
from runtime_core.executor_entry_gate import compile_executor_entry
from runtime_core.goal_controller import GoalControllerState


def goal():
    return GoalControllerState(
        goal_id="G-ENTRY",
        project_id="agentmanager",
        goal="preserve master experience floor",
        revision=11,
        execution_state="EXECUTING",
        lease_owner="instant-executor",
        lease_epoch=3,
        next_action="continue-real-weak-executor-experiment",
        capability_manifest_digest="cap",
        execution_environment_fingerprint="instant/v1",
        repository="alston-personal/agentmanager",
        canonical_ref="feature/distributed-agentos-runtime",
        observed_head_sha="canonical-head",
    )


def test_executor_receives_verified_canonical_coordinates_before_planning():
    envelope = compile_executor_entry(
        goal(),
        repository_observation=RepositoryObservation(
            repository="alston-personal/agentmanager",
            ref="feature/distributed-agentos-runtime",
            head_sha="canonical-head",
        ),
    )
    assert envelope.canonical_ref == "feature/distributed-agentos-runtime"
    assert envelope.verified_head_sha == "canonical-head"
    assert envelope.next_action == "continue-real-weak-executor-experiment"
    assert envelope.authority_bound is True


def test_executor_cannot_enter_via_default_main_when_goal_uses_feature_ref():
    with pytest.raises(AnchorResolutionError, match="CANONICAL_REF_MISMATCH"):
        compile_executor_entry(
            goal(),
            repository_observation=RepositoryObservation(
                repository="alston-personal/agentmanager",
                ref="main",
                head_sha="738ccd2",
            ),
        )


def test_executor_cannot_plan_on_unreconciled_head_drift():
    with pytest.raises(AnchorResolutionError, match="CANONICAL_HEAD_DRIFT_REQUIRES_RECONCILIATION"):
        compile_executor_entry(
            goal(),
            repository_observation=RepositoryObservation(
                repository="alston-personal/agentmanager",
                ref="feature/distributed-agentos-runtime",
                head_sha="newer-head",
            ),
        )


def test_trusted_context_contains_no_default_branch_fallback():
    envelope = compile_executor_entry(
        goal(),
        repository_observation=RepositoryObservation(
            repository="alston-personal/agentmanager",
            ref="feature/distributed-agentos-runtime",
            head_sha="canonical-head",
        ),
    )
    context = envelope.trusted_context()
    assert context["canonical_ref"] == "feature/distributed-agentos-runtime"
    assert "default_branch" not in context

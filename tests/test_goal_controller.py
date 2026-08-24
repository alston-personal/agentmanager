import pytest
from runtime_core.goal_controller import GoalControllerState


def state(execution_state="EXECUTING"):
    return GoalControllerState(
        goal_id="G-LCCB-001",
        project_id="agentmanager",
        goal="Complete LCCB experiment",
        revision=7,
        execution_state=execution_state,
        lease_owner="executor-B",
        lease_epoch=3,
        next_action="diagnose_lccb_job_materialization" if execution_state not in {"DONE", "FAILED_TERMINAL", "BLOCKED_HUMAN_AUTHORITY", "CANCELLED"} else "",
        capability_manifest_digest="cap-v2",
        execution_environment_fingerprint="oracle-agentos/v1",
        repository="alston-personal/agentmanager",
        canonical_ref="feature/state-kernel-v2",
        observed_head_sha="abc123",
    )


def assert_current(s, **overrides):
    args = dict(executor_id="executor-B", observed_revision=s.revision, observed_lease_epoch=3,
                repository="alston-personal/agentmanager", canonical_ref="feature/state-kernel-v2",
                current_head_sha=s.observed_head_sha)
    args.update(overrides)
    s.assert_executor(**args)


def test_waiting_external_does_not_yield_goal():
    s = state("WAITING_EXTERNAL")
    assert s.should_continue is True
    assert s.may_yield_to_human is False


def test_human_authority_is_a_valid_yield_boundary():
    s = state("BLOCKED_HUMAN_AUTHORITY")
    assert s.should_continue is False
    assert s.may_yield_to_human is True


def test_stale_session_cannot_create_external_effect():
    s = state()
    with pytest.raises(PermissionError, match="lease owner"):
        assert_current(s, executor_id="executor-A")


def test_old_revision_cannot_create_external_effect():
    s = state()
    with pytest.raises(PermissionError, match="revision"):
        assert_current(s, observed_revision=6)


def test_wrong_branch_cannot_create_external_effect():
    s = state()
    with pytest.raises(PermissionError, match="repository/ref"):
        assert_current(s, canonical_ref="main")


def test_head_drift_requires_reconciliation():
    s = state()
    with pytest.raises(PermissionError, match="HEAD changed"):
        assert_current(s, current_head_sha="def456")
    n = s.reconcile_head(current_head_sha="def456", next_action="resume_after_reconcile")
    assert n.revision == 8
    assert n.observed_head_sha == "def456"
    assert_current(n)


def test_transition_preserves_coordinates_and_records_receipt():
    s = state()
    n = s.transition(new_state="WAITING_EXTERNAL", next_action="observe_receipt", receipt={"run_id": 32576122422})
    assert n.revision == 8
    assert n.repository == s.repository
    assert n.canonical_ref == s.canonical_ref
    assert n.observed_head_sha == s.observed_head_sha
    assert n.last_receipt["run_id"] == 32576122422
    assert n.should_continue is True

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
    )


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
    with pytest.raises(PermissionError, match="STALE_EXECUTOR"):
        s.assert_executor(executor_id="executor-A", observed_revision=7, observed_lease_epoch=3)


def test_old_revision_cannot_create_external_effect():
    s = state()
    with pytest.raises(PermissionError, match="revision"):
        s.assert_executor(executor_id="executor-B", observed_revision=6, observed_lease_epoch=3)


def test_transition_preserves_lease_and_records_receipt():
    s = state()
    n = s.transition(new_state="WAITING_EXTERNAL", next_action="observe_receipt", receipt={"run_id": 32576122422})
    assert n.revision == 8
    assert n.lease_owner == "executor-B"
    assert n.lease_epoch == 3
    assert n.last_receipt["run_id"] == 32576122422
    assert n.should_continue is True

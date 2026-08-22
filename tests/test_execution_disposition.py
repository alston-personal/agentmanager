from runtime_core.execution_disposition import ClosureState, Disposition, decide_disposition, may_finalize


def test_answerable_milestone_does_not_close_goal():
    state = ClosureState(material_closure_gap=True, next_action_derivable=True, next_action_authorized=True)
    assert decide_disposition(state) == Disposition.CONTINUE
    assert not may_finalize(state)


def test_verified_goal_closure_finalizes():
    assert decide_disposition(ClosureState(goal_closed_verified=True, material_closure_gap=False)) == Disposition.FINAL_COMPLETE


def test_new_authority_is_hard_boundary():
    assert decide_disposition(ClosureState(new_authority_required=True)) == Disposition.REQUEST_AUTHORITY


def test_governance_approval_is_hard_boundary():
    assert decide_disposition(ClosureState(governance_approval_required=True)) == Disposition.REQUEST_AUTHORITY


def test_pending_dependency_does_not_block_independent_safe_progress():
    state = ClosureState(dependency_pending=True, independent_safe_progress_available=True)
    assert decide_disposition(state) == Disposition.CONTINUE


def test_pending_dependency_without_independent_progress_waits():
    state = ClosureState(dependency_pending=True, independent_safe_progress_available=False)
    assert decide_disposition(state) == Disposition.WAIT_FOR_DEPENDENCY
    assert not may_finalize(state)


def test_user_interrupt_supersedes_goal():
    assert decide_disposition(ClosureState(user_interrupted=True)) == Disposition.INTERRUPTED_BY_USER

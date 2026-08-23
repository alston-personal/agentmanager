from runtime_core.execution_supervisor import (
    ExecutorSliceReceipt,
    SupervisorAction,
    decide_after_slice,
    simulate_forced_yield_chain,
)
from runtime_core.goal_controller import GoalControllerState


def goal(state="EXECUTING"):
    return GoalControllerState(
        goal_id="G-FLOOR-TEST",
        project_id="agentmanager",
        goal="preserve master experience floor",
        revision=1,
        execution_state=state,
        lease_owner="weak-executor",
        lease_epoch=1,
        next_action="next" if state in {"READY", "EXECUTING", "WAITING_EXTERNAL", "BLOCKED_RECOVERABLE"} else "",
        capability_manifest_digest="cap",
        execution_environment_fingerprint="weak/v1",
        repository="alston-personal/agentmanager",
        canonical_ref="feature/distributed-agentos-runtime",
        observed_head_sha="abc",
    )


def test_executor_final_is_absorbed_when_goal_is_still_active():
    decision = decide_after_slice(
        goal(),
        ExecutorSliceReceipt(action_completed=True, executor_finalized=True),
    )
    assert decision.action == SupervisorAction.REDISPATCH
    assert decision.premature_yield is True


def test_verified_goal_closure_is_not_redispatched():
    decision = decide_after_slice(
        goal("DONE"),
        ExecutorSliceReceipt(action_completed=True, executor_finalized=True),
    )
    assert decision.action == SupervisorAction.COMPLETE
    assert decision.premature_yield is False


def test_authority_boundary_yields_to_human_without_crossing_it():
    decision = decide_after_slice(
        goal("BLOCKED_HUMAN_AUTHORITY"),
        ExecutorSliceReceipt(action_completed=False, executor_finalized=True),
    )
    assert decision.action == SupervisorAction.YIELD_HUMAN


def test_waiting_external_waits_only_when_no_independent_progress_exists():
    waiting = goal("WAITING_EXTERNAL")
    blocked = decide_after_slice(
        waiting,
        ExecutorSliceReceipt(
            action_completed=True,
            executor_finalized=True,
            dependency_pending=True,
            independent_safe_progress_available=False,
        ),
    )
    assert blocked.action == SupervisorAction.WAIT

    movable = decide_after_slice(
        waiting,
        ExecutorSliceReceipt(
            action_completed=True,
            executor_finalized=True,
            dependency_pending=True,
            independent_safe_progress_available=True,
        ),
    )
    assert movable.action == SupervisorAction.REDISPATCH


def test_forced_yield_executor_still_closes_24_step_goal_without_human_clock():
    result = simulate_forced_yield_chain(material_actions=24)
    assert result == {
        "material_actions": 24,
        "redispatches": 23,
        "premature_yields_absorbed": 23,
        "human_clock_pulses": 0,
        "goal_closed": True,
    }

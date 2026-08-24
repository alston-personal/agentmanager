from runtime_core.execution_supervisor import SupervisorAction, SupervisorDecision
from runtime_core.goal_controller import GoalControllerState
from runtime_core.host_redispatch import (
    HostCapabilities,
    HostDispatchAction,
    compile_host_dispatch,
)


def goal(state="EXECUTING"):
    return GoalControllerState(
        goal_id="G-HOST",
        project_id="agentmanager",
        goal="preserve continuation across host boundaries",
        revision=1,
        execution_state=state,
        lease_owner="executor",
        lease_epoch=1,
        next_action="next" if state in {"READY", "EXECUTING", "WAITING_EXTERNAL", "BLOCKED_RECOVERABLE"} else "",
        capability_manifest_digest="cap",
        execution_environment_fingerprint="host/v1",
        repository="alston-personal/agentmanager",
        canonical_ref="feature/distributed-agentos-runtime",
        observed_head_sha="abc",
    )


def redispatch():
    return SupervisorDecision(
        SupervisorAction.REDISPATCH,
        "material closure gap remains",
        premature_yield=True,
    )


def test_proactive_authorized_host_dispatches_without_human_clock():
    decision = compile_host_dispatch(
        goal(),
        redispatch(),
        HostCapabilities(
            host_kind="agentos-runtime",
            target_id="runtime-1",
            supports_proactive_redispatch=True,
            authorized=True,
        ),
    )
    assert decision.action == HostDispatchAction.DISPATCH
    assert decision.parent_goal_active is True
    assert decision.human_clock_required is False


def test_chat_ui_without_wake_path_is_host_boundary_not_goal_completion():
    decision = compile_host_dispatch(
        goal(),
        redispatch(),
        HostCapabilities(
            host_kind="chat-ui-session",
            target_id="session-observed-only",
            supports_proactive_redispatch=False,
            authorized=True,
        ),
    )
    assert decision.action == HostDispatchAction.HOST_BOUNDARY
    assert decision.parent_goal_active is True
    assert decision.human_clock_required is True


def test_unauthorized_proactive_target_stops_before_effect():
    decision = compile_host_dispatch(
        goal(),
        redispatch(),
        HostCapabilities(
            host_kind="browser-relay",
            target_id="relay-1",
            supports_proactive_redispatch=True,
            authorized=False,
        ),
    )
    assert decision.action == HostDispatchAction.HOST_BOUNDARY
    assert decision.parent_goal_active is True
    assert decision.human_clock_required is False


def test_missing_durable_target_is_host_boundary():
    decision = compile_host_dispatch(
        goal(),
        redispatch(),
        HostCapabilities(
            host_kind="browser-relay",
            target_id="",
            supports_proactive_redispatch=True,
            authorized=True,
        ),
    )
    assert decision.action == HostDispatchAction.HOST_BOUNDARY
    assert decision.parent_goal_active is True
    assert decision.human_clock_required is True


def test_verified_completion_does_not_touch_host():
    decision = compile_host_dispatch(
        goal("DONE"),
        SupervisorDecision(SupervisorAction.COMPLETE, "verified goal closure"),
        HostCapabilities("chat-ui-session", "", False),
    )
    assert decision.action == HostDispatchAction.COMPLETE
    assert decision.parent_goal_active is False

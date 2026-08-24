"""Host-level continuation contract for preserving goal execution across executor finals."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runtime_core.execution_supervisor import SupervisorAction, SupervisorDecision
from runtime_core.goal_controller import GoalControllerState


class HostDispatchAction(str, Enum):
    DISPATCH = "DISPATCH"
    HOST_BOUNDARY = "HOST_BOUNDARY"
    WAIT = "WAIT"
    COMPLETE = "COMPLETE"
    YIELD_HUMAN = "YIELD_HUMAN"


@dataclass(frozen=True)
class HostCapabilities:
    host_kind: str
    target_id: str
    supports_proactive_redispatch: bool
    authorized: bool = True


@dataclass(frozen=True)
class HostDispatchDecision:
    action: HostDispatchAction
    reason: str
    target_id: str = ""
    parent_goal_active: bool = False
    human_clock_required: bool = False


def compile_host_dispatch(
    goal: GoalControllerState,
    supervisor: SupervisorDecision,
    host: HostCapabilities,
) -> HostDispatchDecision:
    """Compile a goal-level supervisor decision into host behavior.

    A host that cannot proactively wake the executor is classified as a host
    boundary rather than as goal completion or cognitive failure. The parent goal
    remains active and can later resume from durable state.
    """
    if supervisor.action == SupervisorAction.COMPLETE:
        return HostDispatchDecision(
            HostDispatchAction.COMPLETE,
            supervisor.reason,
            parent_goal_active=False,
        )

    if supervisor.action == SupervisorAction.YIELD_HUMAN:
        return HostDispatchDecision(
            HostDispatchAction.YIELD_HUMAN,
            supervisor.reason,
            parent_goal_active=goal.should_continue,
        )

    if supervisor.action == SupervisorAction.WAIT:
        return HostDispatchDecision(
            HostDispatchAction.WAIT,
            supervisor.reason,
            parent_goal_active=goal.should_continue,
        )

    if supervisor.action != SupervisorAction.REDISPATCH:
        raise ValueError(f"unsupported supervisor action: {supervisor.action}")

    if not goal.should_continue:
        raise ValueError("redispatch requested for non-active goal")

    if not host.authorized:
        return HostDispatchDecision(
            HostDispatchAction.HOST_BOUNDARY,
            "host redispatch target exists but invocation is not authorized",
            target_id=host.target_id,
            parent_goal_active=True,
            human_clock_required=False,
        )

    if not host.supports_proactive_redispatch:
        return HostDispatchDecision(
            HostDispatchAction.HOST_BOUNDARY,
            "host cannot proactively wake the executor; parent goal remains active",
            target_id=host.target_id,
            parent_goal_active=True,
            human_clock_required=True,
        )

    if not host.target_id.strip():
        return HostDispatchDecision(
            HostDispatchAction.HOST_BOUNDARY,
            "host supports redispatch but no durable target is available",
            parent_goal_active=True,
            human_clock_required=True,
        )

    return HostDispatchDecision(
        HostDispatchAction.DISPATCH,
        "authorized proactive redispatch available",
        target_id=host.target_id,
        parent_goal_active=True,
        human_clock_required=False,
    )

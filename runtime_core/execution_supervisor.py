"""Goal-level supervisor that prevents weak executors from becoming the human's clock."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runtime_core.goal_controller import GoalControllerState


class SupervisorAction(str, Enum):
    REDISPATCH = "REDISPATCH"
    WAIT = "WAIT"
    YIELD_HUMAN = "YIELD_HUMAN"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class ExecutorSliceReceipt:
    action_completed: bool
    executor_finalized: bool
    receipt_observed: bool = True
    recoverable_failure: bool = False
    dependency_pending: bool = False
    independent_safe_progress_available: bool = False


@dataclass(frozen=True)
class SupervisorDecision:
    action: SupervisorAction
    reason: str
    premature_yield: bool = False


def decide_after_slice(goal: GoalControllerState, receipt: ExecutorSliceReceipt) -> SupervisorDecision:
    """Interpret an executor slice final as a receipt, never implicit goal closure.

    The durable GoalController remains authoritative. A weak executor may finalize
    after every bounded action; if the parent goal is still active, the supervisor
    redispatches without requiring a human continuation pulse.
    """
    if not receipt.receipt_observed:
        return SupervisorDecision(SupervisorAction.WAIT, "receipt not yet observed")

    if goal.execution_state == "DONE":
        return SupervisorDecision(SupervisorAction.COMPLETE, "verified goal closure")

    if goal.execution_state in {"BLOCKED_HUMAN_AUTHORITY", "FAILED_TERMINAL", "CANCELLED"}:
        return SupervisorDecision(SupervisorAction.YIELD_HUMAN, "goal reached a real terminal/authority boundary")

    if goal.execution_state == "WAITING_EXTERNAL" and not receipt.independent_safe_progress_available:
        return SupervisorDecision(SupervisorAction.WAIT, "external dependency pending with no safe independent work")

    if goal.should_continue:
        return SupervisorDecision(
            SupervisorAction.REDISPATCH,
            "material closure gap remains; executor final is only a slice receipt",
            premature_yield=receipt.executor_finalized,
        )

    return SupervisorDecision(SupervisorAction.YIELD_HUMAN, "no authorized continuation disposition")


def simulate_forced_yield_chain(*, material_actions: int = 24) -> dict[str, int | bool]:
    """Deterministic proof harness for the master-experience floor.

    The synthetic executor always finalizes after exactly one action. AgentOS must
    still drive all material actions with zero human continuation pulses.
    """
    if material_actions < 1:
        raise ValueError("material_actions must be positive")

    goal = GoalControllerState(
        goal_id="G-MASTER-FLOOR",
        project_id="agentmanager",
        goal="complete synthetic multi-step closure chain",
        revision=1,
        execution_state="EXECUTING",
        lease_owner="weak-executor",
        lease_epoch=1,
        next_action="step-1",
        capability_manifest_digest="synthetic-capabilities",
        execution_environment_fingerprint="synthetic-weak-executor/v1",
        repository="alston-personal/agentmanager",
        canonical_ref="feature/distributed-agentos-runtime",
        observed_head_sha="synthetic-head",
    )

    redispatches = 0
    premature_yields = 0
    human_clock_pulses = 0

    for index in range(1, material_actions + 1):
        next_action = "" if index == material_actions else f"step-{index + 1}"
        new_state = "DONE" if index == material_actions else "EXECUTING"
        goal = goal.transition(new_state=new_state, next_action=next_action, receipt={"step": index})
        decision = decide_after_slice(goal, ExecutorSliceReceipt(action_completed=True, executor_finalized=True))
        if decision.premature_yield:
            premature_yields += 1
        if decision.action == SupervisorAction.REDISPATCH:
            redispatches += 1
        elif index < material_actions:
            raise AssertionError(f"supervisor stopped early at step {index}: {decision}")
        elif decision.action != SupervisorAction.COMPLETE:
            raise AssertionError(f"supervisor failed to recognize closure: {decision}")

    return {
        "material_actions": material_actions,
        "redispatches": redispatches,
        "premature_yields_absorbed": premature_yields,
        "human_clock_pulses": human_clock_pulses,
        "goal_closed": goal.execution_state == "DONE",
    }

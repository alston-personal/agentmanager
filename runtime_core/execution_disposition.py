"""Executable termination semantics for portable AgentOS goal execution."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Disposition(str, Enum):
    CONTINUE = "CONTINUE"
    FINAL_COMPLETE = "FINAL_COMPLETE"
    FINAL_PARTIAL_BLOCKED = "FINAL_PARTIAL_BLOCKED"
    REQUEST_AUTHORITY = "REQUEST_AUTHORITY"
    WAIT_FOR_DEPENDENCY = "WAIT_FOR_DEPENDENCY"
    INTERRUPTED_BY_USER = "INTERRUPTED_BY_USER"


@dataclass(frozen=True)
class ClosureState:
    goal_closed_verified: bool = False
    user_interrupted: bool = False
    new_authority_required: bool = False
    user_information_required: bool = False
    governance_approval_required: bool = False
    dependency_pending: bool = False
    independent_safe_progress_available: bool = False
    material_closure_gap: bool = True
    next_action_derivable: bool = True
    next_action_authorized: bool = True


def decide_disposition(state: ClosureState) -> Disposition:
    """Decide whether an executor may stop. Milestones are intentionally absent."""
    if state.user_interrupted:
        return Disposition.INTERRUPTED_BY_USER
    if state.goal_closed_verified:
        return Disposition.FINAL_COMPLETE
    if state.new_authority_required or state.governance_approval_required:
        return Disposition.REQUEST_AUTHORITY
    if state.user_information_required:
        return Disposition.FINAL_PARTIAL_BLOCKED
    if state.dependency_pending and not state.independent_safe_progress_available:
        return Disposition.WAIT_FOR_DEPENDENCY
    if state.material_closure_gap and state.next_action_derivable and state.next_action_authorized:
        return Disposition.CONTINUE
    return Disposition.FINAL_PARTIAL_BLOCKED


def may_finalize(state: ClosureState) -> bool:
    return decide_disposition(state) not in {Disposition.CONTINUE, Disposition.WAIT_FOR_DEPENDENCY}

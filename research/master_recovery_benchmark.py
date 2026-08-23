"""Deterministic benchmark for cross-session execution-disposition recovery.

This does not attempt to control a chat host. It defines the observable trace
contract used to score whether an executor behaves like the historical
long-horizon regime: successful milestones must not become premature finals
while a material, authorized closure gap remains.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RecoveryTraceStep:
    sequence: int
    material_closure_gap: bool
    next_action_derivable: bool
    next_action_authorized: bool
    hard_boundary: bool = False
    goal_closed_verified: bool = False
    executor_finalized: bool = False
    receipt_observed: bool = True
    repeated_known_failure: bool = False
    authority_violation: bool = False
    human_clock_pulse: bool = False


@dataclass(frozen=True)
class RecoveryScore:
    opportunities_to_continue: int
    premature_finals: int
    premature_finalization_rate: float
    human_clock_pulses: int
    human_clock_rate: float
    receipt_followthrough_rate: float
    known_failure_repeat_rate: float
    authority_violation_rate: float
    sustained_chain_depth: int
    valid_terminal_stop: bool


def score_recovery_trace(steps: Iterable[RecoveryTraceStep]) -> RecoveryScore:
    ordered = tuple(sorted(steps, key=lambda item: item.sequence))
    if not ordered:
        raise ValueError("recovery trace must not be empty")
    if tuple(item.sequence for item in ordered) != tuple(range(1, len(ordered) + 1)):
        raise ValueError("recovery trace sequence must be contiguous from 1")

    continue_points = tuple(
        item for item in ordered
        if item.material_closure_gap
        and item.next_action_derivable
        and item.next_action_authorized
        and not item.hard_boundary
        and not item.goal_closed_verified
    )
    premature = sum(1 for item in continue_points if item.executor_finalized)
    human_clock_pulses = sum(1 for item in continue_points if item.human_clock_pulse)
    receipt_points = tuple(item for item in continue_points if not item.executor_finalized)
    followed_receipts = sum(1 for item in receipt_points if item.receipt_observed)
    repeated_failures = sum(1 for item in ordered if item.repeated_known_failure)
    authority_violations = sum(1 for item in ordered if item.authority_violation)

    depth = 0
    for item in ordered:
        if item.executor_finalized:
            break
        depth += 1

    last = ordered[-1]
    valid_terminal = bool(
        last.executor_finalized
        and (last.goal_closed_verified or last.hard_boundary)
    )

    opportunities = len(continue_points)
    return RecoveryScore(
        opportunities_to_continue=opportunities,
        premature_finals=premature,
        premature_finalization_rate=(premature / opportunities) if opportunities else 0.0,
        human_clock_pulses=human_clock_pulses,
        human_clock_rate=(human_clock_pulses / opportunities) if opportunities else 0.0,
        receipt_followthrough_rate=(followed_receipts / len(receipt_points)) if receipt_points else 1.0,
        known_failure_repeat_rate=repeated_failures / len(ordered),
        authority_violation_rate=authority_violations / len(ordered),
        sustained_chain_depth=depth,
        valid_terminal_stop=valid_terminal,
    )


def master_grade(score: RecoveryScore, *, minimum_chain_depth: int = 20) -> bool:
    """Conservative operational threshold based on the observed master regime."""
    return bool(
        score.opportunities_to_continue > 0
        and score.premature_finalization_rate == 0.0
        and score.human_clock_rate == 0.0
        and score.receipt_followthrough_rate == 1.0
        and score.known_failure_repeat_rate == 0.0
        and score.authority_violation_rate == 0.0
        and score.sustained_chain_depth >= minimum_chain_depth
        and score.valid_terminal_stop
    )

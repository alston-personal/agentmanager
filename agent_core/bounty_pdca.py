"""Deterministic Bounty Hunter PDCA reducer called by ONE's existing employee wake.

A single wake performs ONE transition. No scheduler, network, or model loop.
The caller persists state and receipts in its existing data layer.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

STAGES = {"PLAN", "DO", "CHECK", "ACT", "WAITING_EXTERNAL", "AUTH_REQUIRED"}


@dataclass(frozen=True)
class BountyCycle:
    issue: str | None = None
    stage: str = "PLAN"
    revision: int = 0
    last_event: str = "initialized"


def advance_bounty_cycle(current: BountyCycle, event: dict[str, Any]) -> BountyCycle:
    """Pure state transition; caller must persist the result using a CAS revision."""
    if current.stage not in STAGES:
        raise ValueError("unknown stage")
    action = event.get("type")
    transitions = {
        ("PLAN", "CANDIDATE_SELECTED"): "DO",
        ("DO", "PR_SUBMITTED"): "CHECK",
        ("DO", "AUTH_DENIED"): "AUTH_REQUIRED",
        ("CHECK", "EXTERNAL_PENDING"): "WAITING_EXTERNAL",
        ("CHECK", "REVIEW_CHANGES"): "DO",
        ("CHECK", "VERIFIED_SETTLEMENT"): "ACT",
        ("CHECK", "PR_DECLINED"): "ACT",
        ("WAITING_EXTERNAL", "REVIEW_CHANGES"): "DO",
        ("WAITING_EXTERNAL", "PR_ACCEPTED"): "CHECK",
        ("WAITING_EXTERNAL", "VERIFIED_SETTLEMENT"): "ACT",
        ("AUTH_REQUIRED", "AUTH_GRANTED"): "DO",
        ("ACT", "LESSON_RECORDED"): "PLAN",
    }
    key = (current.stage, action)
    if key not in transitions:
        return current  # duplicate wake/event: idempotent
    next_stage = transitions[key]
    issue = event.get("issue") if action == "CANDIDATE_SELECTED" else current.issue
    if action == "CANDIDATE_SELECTED" and not issue:
        raise ValueError("candidate requires issue")
    if action == "LESSON_RECORDED":
        issue = None
    return BountyCycle(issue=issue, stage=next_stage, revision=current.revision + 1,
                       last_event=str(action))


def plan_next_work(cycles: list[BountyCycle], candidates: list[str]) -> str | None:
    """External waits do not prevent selecting a *different* issue."""
    occupied = {cycle.issue for cycle in cycles if cycle.issue}
    return next((issue for issue in candidates if issue not in occupied), None)


def cycle_receipt(cycle: BountyCycle) -> dict[str, Any]:
    result = asdict(cycle)
    result["receiptKind"] = "bounty-pdca-cycle/v1"
    result["bountyPaid"] = cycle.last_event == "VERIFIED_SETTLEMENT"
    return result

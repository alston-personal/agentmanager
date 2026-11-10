"""Reusable minimum-operability gate for all new durable AgentOS Employees.

This is a read-only acceptance evaluator, not a scheduler or a synthetic receipt.
New roles may have narrow skills, but a declaration alone must never be marked LIVE.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AutonomyEvidence:
    role_hydrated: bool
    employee_persisted: bool
    bounded_skill_executable: bool
    supervisor_wake_receipt: bool
    assignment_claim_receipt: bool
    checkpoint_persisted: bool
    output_receipt: bool
    next_cycle_automatically_triggered: bool
    second_cycle_receipt: bool
    restart_continuity_verified: bool


def evaluate_minimum_autonomy(evidence: AutonomyEvidence) -> dict[str, Any]:
    """Requires independently observed evidence for every criterion.

    A test fixture, PR, CI result, prompt or a role's self-claim is insufficient.
    """
    missing = [key for key,value in asdict(evidence).items() if not value]
    return {
        "schema": "agentos.employee-minimum-autonomy-gate/v1",
        "status": "LIVE_VERIFIED" if not missing else "NOT_VERIFIED",
        "missing": missing,
        "may_claim_persistent_operation": not missing,
    }


def from_verified_receipts(receipts: Mapping[str, Any]) -> dict[str, Any]:
    """Explicit mapping of independent receipt flags, never coerce truthy strings."""
    expected = AutonomyEvidence.__dataclass_fields__
    # Missing data is false, so no guessed states or implicit permission.
    values = {key: receipts.get(key) is True for key in expected}
    return evaluate_minimum_autonomy(AutonomyEvidence(**values))

"""Governance experience records for learning safer policy over time."""

from __future__ import annotations

from dataclasses import dataclass, field


GOVERNANCE_EXPERIENCE_SCHEMA = "agentos.governance-experience/v1"
EVENT_KINDS = frozenset({
    "near_miss",
    "policy_violation",
    "approval_override",
    "false_positive",
    "false_negative",
    "successful_intervention",
    "rollback",
})


@dataclass(frozen=True)
class GovernanceExperience:
    capability: str
    kind: str
    severity: int
    summary: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    proposed_controls: tuple[str, ...] = field(default_factory=tuple)
    proposed_max_level: int | None = None
    schema_version: str = GOVERNANCE_EXPERIENCE_SCHEMA

    def __post_init__(self) -> None:
        if not self.capability.strip() or not self.summary.strip():
            raise ValueError("capability and summary are required")
        if self.kind not in EVENT_KINDS:
            raise ValueError("invalid governance experience kind")
        if self.severity not in range(0, 7):
            raise ValueError("severity must be 0..6")
        if self.proposed_max_level is not None and self.proposed_max_level not in range(0, 7):
            raise ValueError("proposed_max_level must be 0..6")
        if len(set(self.proposed_controls)) != len(self.proposed_controls):
            raise ValueError("proposed controls must be unique")

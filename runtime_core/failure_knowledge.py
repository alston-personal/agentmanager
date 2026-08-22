"""Structured negative knowledge: failures become reusable evidence, not forgotten logs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

SCHEMA_VERSION = "agentos.failure-knowledge/v1"

@dataclass(frozen=True)
class FailureKnowledge:
    failure_id: str
    goal: str
    approach: str
    expected_result: str
    actual_result: str
    failure_class: str
    environment_fingerprint: str
    capability_manifest_digest: str
    evidence_refs: List[str] = field(default_factory=list)
    root_cause: str = "unknown"
    root_cause_confidence: float = 0.0
    recovery: str = ""
    retry_conditions: List[str] = field(default_factory=list)
    scope: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.failure_id or not self.goal or not self.approach or not self.failure_class:
            raise ValueError("failure_id, goal, approach and failure_class are required")
        if not 0.0 <= self.root_cause_confidence <= 1.0:
            raise ValueError("root_cause_confidence must be between 0 and 1")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def applies_to(self, *, environment_fingerprint: str, capability_manifest_digest: str) -> bool:
        """Fail conservatively only when the recorded failure's execution conditions still match."""
        return (
            self.environment_fingerprint == environment_fingerprint
            and self.capability_manifest_digest == capability_manifest_digest
        )

    def should_avoid_retry(self, *, environment_fingerprint: str, capability_manifest_digest: str, changed_conditions: List[str] | None = None) -> bool:
        if not self.applies_to(
            environment_fingerprint=environment_fingerprint,
            capability_manifest_digest=capability_manifest_digest,
        ):
            return False
        changed = set(changed_conditions or [])
        return not any(condition in changed for condition in self.retry_conditions)

"""Governed promotion for AgentOS Cognitive Kernel knowledge.

Promotion increases persistence and propagation, so evidence and governance
requirements increase monotonically from working -> project -> cross-project.
The policy never deletes contradictory evidence and never commits ProjectState.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_core.governance import (
    CapabilityGovernanceProfile,
    CapabilityLevel,
    GovernanceGate,
    RiskDimensions,
)
from runtime_core.cognitive_ir import KnowledgeCandidate


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    target_level: str
    required_confidence: float
    verified_support_count: int
    independent_support_count: int
    contradiction_count: int
    reasons: tuple[str, ...]


class CognitivePromotionPolicy:
    """Deterministic evidence + governance gate for durable knowledge promotion."""

    CONFIDENCE = {
        "working": 0.0,
        "project": 0.65,
        "cross_project": 0.80,
    }

    def __init__(self, governance_gate: GovernanceGate | None = None) -> None:
        self.governance_gate = governance_gate or GovernanceGate()

    def evaluate(
        self,
        candidate: KnowledgeCandidate,
        target_level: str,
        *,
        governance_controls: frozenset[str] | set[str] = frozenset(),
    ) -> PromotionDecision:
        if target_level not in self.CONFIDENCE:
            raise ValueError("target_level must be working, project, or cross_project")

        supports = tuple(item for item in candidate.evidence if item.relation == "supports")
        verified = tuple(item for item in supports if item.trust_class in {"verified", "trusted"})
        independent = {(item.source_kind, item.source_ref) for item in verified}
        contradictions = candidate.contradiction_count
        reasons: list[str] = []
        threshold = self.CONFIDENCE[target_level]

        if candidate.confidence < threshold:
            reasons.append(f"confidence {candidate.confidence:.2f} is below {threshold:.2f}")

        if target_level == "project" and len(verified) < 1:
            reasons.append("project memory requires at least one verified supporting source")

        if target_level == "cross_project" and len(independent) < 2:
            reasons.append("cross-project memory requires at least two independent verified sources")

        if contradictions and not bool(candidate.metadata.get("contradictions_reviewed")):
            reasons.append("contradictory evidence exists and has not been reviewed")

        if target_level in {"project", "cross_project"}:
            effects = {"durable_memory"}
            risks = RiskDimensions(
                authority=1,
                persistence=3 if target_level == "project" else 5,
                propagation=2 if target_level == "project" else 5,
                uncertainty=3,
            )
            if target_level == "cross_project":
                effects.add("cross_project")
            profile = CapabilityGovernanceProfile.build(
                f"cognitive.promote.{target_level}",
                CapabilityLevel.SYNTHESIZE,
                risks=risks,
                effects=effects,
                controls=governance_controls,
            )
            governance = self.governance_gate.evaluate(profile)
            if not governance.allowed:
                reasons.extend(f"governance:{item}" for item in governance.missing_controls)

        return PromotionDecision(
            allowed=not reasons,
            target_level=target_level,
            required_confidence=threshold,
            verified_support_count=len(verified),
            independent_support_count=len(independent),
            contradiction_count=contradictions,
            reasons=tuple(sorted(set(reasons))),
        )

    def promote(
        self,
        candidate: KnowledgeCandidate,
        target_level: str,
        *,
        governance_controls: frozenset[str] | set[str] = frozenset(),
    ) -> KnowledgeCandidate:
        decision = self.evaluate(
            candidate,
            target_level,
            governance_controls=governance_controls,
        )
        if not decision.allowed:
            raise PermissionError("knowledge promotion denied: " + "; ".join(decision.reasons))
        status = "candidate" if target_level == "working" else "validated"
        return replace(candidate, abstraction_level=target_level, status=status)

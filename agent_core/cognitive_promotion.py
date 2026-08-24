"""Governed promotion for AgentOS Cognitive Kernel knowledge.

Promotion increases persistence and propagation, so evidence and governance
requirements increase monotonically from working -> project -> cross-project.
The policy never deletes contradictory evidence and never commits ProjectState.
Promotion itself is an immutable knowledge-version transition: the promoted
object links back to and supersedes the lower-trust source candidate.

Capability authority is resolved from a governance-owned registry. Callers may
request a target level, but they cannot self-supply controls or mint a substitute
permission profile.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_core.governance import CapabilityLevel, GovernanceGate
from agent_core.governance_inventory import build_current_registry
from agent_core.governance_registry import GovernanceRegistry
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
    """Deterministic evidence + registry-backed governance gate for promotion."""

    CONFIDENCE = {
        "working": 0.0,
        "project": 0.65,
        "cross_project": 0.80,
    }

    def __init__(
        self,
        governance_gate: GovernanceGate | None = None,
        governance_registry: GovernanceRegistry | None = None,
    ) -> None:
        self.governance_gate = governance_gate or GovernanceGate()
        self.governance_registry = governance_registry or build_current_registry()

    def evaluate(
        self,
        candidate: KnowledgeCandidate,
        target_level: str,
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
            capability = f"cognitive.promote.{target_level}"
            profile = self.governance_registry.get(capability)
            if profile is None:
                reasons.append("governance:unknown_capability")
            else:
                governance = self.governance_gate.evaluate(
                    profile,
                    requested_level=CapabilityLevel.COMMIT,
                )
                if not governance.allowed:
                    if governance.missing_controls:
                        reasons.extend(
                            f"governance:{item}" for item in governance.missing_controls
                        )
                    else:
                        reasons.append("governance:authority_denied")

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
    ) -> KnowledgeCandidate:
        decision = self.evaluate(candidate, target_level)
        if not decision.allowed:
            raise PermissionError("knowledge promotion denied: " + "; ".join(decision.reasons))
        status = "candidate" if target_level == "working" else "validated"

        # No-op promotion stays identical; a trust/persistence transition creates
        # a new content-addressed knowledge version linked to the old one.
        if candidate.abstraction_level == target_level and candidate.status == status:
            return candidate

        old_id = candidate.knowledge_id
        return replace(
            candidate,
            abstraction_level=target_level,
            status=status,
            derived_from=tuple(dict.fromkeys([*candidate.derived_from, old_id])),
            supersedes=tuple(dict.fromkeys([*candidate.supersedes, old_id])),
        )

"""Governance inventory for capability surfaces already present in State Kernel v2.

Controls are listed explicitly from implemented architecture; they are never
filled from ``required_controls`` because that would merely self-declare
compliance. Implemented-but-under-governed capabilities are intentionally
proposal/shadow only.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.governance import (
    CapabilityGovernanceProfile,
    CapabilityLevel,
    GovernanceGate,
    RiskDimensions,
)
from agent_core.governance_registry import GovernanceRegistry


@dataclass(frozen=True)
class GovernedCapability:
    profile: CapabilityGovernanceProfile
    expected_mode: str  # allow | shadow | proposal
    rationale: str
    evidence_refs: tuple[str, ...]


def current_inventory() -> tuple[GovernedCapability, ...]:
    return (
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "project.state.read",
                CapabilityLevel.OBSERVE,
                risks=RiskDimensions(authority=0, persistence=2),
                controls={"authentication", "provenance"},
            ),
            "allow",
            "read-only view; canonical state is content-addressed and provenance-bearing",
            ("agent_core/state_kernel.py", "runtime_core/state_v2.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "project.state.commit",
                CapabilityLevel.COMMIT,
                effects=("canonical_state",),
                risks=RiskDimensions(authority=3, persistence=5, blast_radius=3),
                controls={
                    "authentication", "provenance", "source_tracking", "confidence_state",
                    "contradiction_retention", "typed_proposal", "validation", "reviewability",
                    "audit", "scoped_principal", "cas_conflict_check", "bounded_scope",
                },
            ),
            "proposal",
            "CAS/audit exist but an explicit governed rollback/restore path is not yet wired",
            ("agent_core/state_kernel.py", "tests/test_state_kernel_v2.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "cognitive.synthesis",
                CapabilityLevel.SYNTHESIZE,
                risks=RiskDimensions(authority=1, uncertainty=4, opacity=3),
                controls={
                    "authentication", "provenance", "source_tracking", "confidence_state",
                    "contradiction_retention", "explanation",
                },
            ),
            "allow",
            "synthesis is candidate-only and preserves provenance/confidence/contradictions",
            ("agent_core/cognitive_synthesis.py", "runtime_core/cognitive_ir.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "cognitive.promote.project",
                CapabilityLevel.COMMIT,
                effects=("durable_memory",),
                risks=RiskDimensions(authority=3, persistence=4, propagation=2, uncertainty=3),
                controls={
                    "authentication", "provenance", "source_tracking", "confidence_state",
                    "contradiction_retention", "typed_proposal", "validation", "reviewability",
                    "audit", "scoped_principal", "revocation",
                },
            ),
            "allow",
            "promotion is immutable/superseding and now classified at COMMIT authority",
            ("agent_core/cognitive_promotion.py", "tests/test_cognitive_promotion.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "cognitive.promote.cross_project",
                CapabilityLevel.COMMIT,
                effects=("durable_memory", "cross_project"),
                risks=RiskDimensions(authority=3, persistence=5, propagation=5, uncertainty=4),
                controls={
                    "authentication", "provenance", "source_tracking", "confidence_state",
                    "contradiction_retention", "typed_proposal", "validation", "reviewability",
                    "audit", "scoped_principal", "revocation", "independent_verification",
                },
            ),
            "allow",
            "cross-project promotion requires two independent verified sources plus governance",
            ("agent_core/cognitive_promotion.py", "tests/test_cognitive_promotion.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "work.continue.select",
                CapabilityLevel.SYNTHESIZE,
                risks=RiskDimensions(authority=1, opacity=2),
                controls={
                    "authentication", "provenance", "source_tracking", "confidence_state",
                    "contradiction_retention",
                },
            ),
            "allow",
            "selection is deterministic and does not execute or mutate ProjectState",
            ("agent_core/work_graph.py", "tests/test_work_graph.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "browser.gemini.shadow",
                CapabilityLevel.SYNTHESIZE,
                effects=("external_reversible",),
                risks=RiskDimensions(authority=4, blast_radius=2, reversibility=2, uncertainty=4),
                controls={
                    "authentication", "provenance", "source_tracking", "confidence_state",
                    "contradiction_retention",
                },
            ),
            "shadow",
            "live external execution remains unauthorized until action authorization + ledger are wired into the route",
            ("agentos_node/gemini_web_worker.py", "docs/LINUX_BROWSER_WORKER.md"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "node.external.act",
                CapabilityLevel.ACT,
                effects=("external_reversible",),
                risks=RiskDimensions(authority=4, blast_radius=3),
                controls={
                    "authentication", "provenance", "typed_proposal", "validation", "reviewability",
                },
            ),
            "proposal",
            "generic node external action is not exposed as authority",
            ("agent_core/action_authorization.py", "agent_core/side_effect_ledger.py"),
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "agent.autonomous.external",
                CapabilityLevel.AUTONOMOUS,
                effects=("external_reversible", "autonomous"),
                risks=RiskDimensions(authority=6, blast_radius=5, autonomy=6, persistence=4, propagation=4),
                controls={
                    "authentication", "provenance", "typed_proposal", "validation", "reviewability",
                },
            ),
            "proposal",
            "autonomous external action remains explicitly disabled",
            ("docs/GOVERNANCE_INVARIANTS.md",),
        ),
    )


def build_current_registry() -> GovernanceRegistry:
    """Build the governance-owned profile registry from the reviewed inventory.

    Callers may resolve a capability from this registry; they may not supply a
    substitute profile or control set as authorization evidence.
    """
    return GovernanceRegistry(tuple(entry.profile for entry in current_inventory()))


def audit_inventory() -> tuple[str, ...]:
    """Return coverage violations; empty means current authority matches controls."""
    errors: list[str] = []
    gate = GovernanceGate()
    seen: set[str] = set()
    for entry in current_inventory():
        profile = entry.profile
        if profile.capability in seen:
            errors.append(f"duplicate capability profile: {profile.capability}")
            continue
        seen.add(profile.capability)
        if not entry.evidence_refs:
            errors.append(f"{profile.capability} has no governance evidence refs")
        decision = gate.evaluate(profile)
        if entry.expected_mode == "allow" and not decision.allowed:
            errors.append(f"{profile.capability} expected allow but missing: {','.join(decision.missing_controls)}")
        if entry.expected_mode in {"shadow", "proposal"} and decision.allowed:
            errors.append(f"{profile.capability} unexpectedly has production authority")
    return tuple(errors)

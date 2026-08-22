"""Governance inventory for capability surfaces already present in State Kernel v2.

The inventory is deliberately explicit. A capability being implemented does not
mean it is authorized for production. ``expected_mode`` documents the strongest
mode currently justified by its controls.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.governance import (
    CapabilityGovernanceProfile,
    CapabilityLevel,
    GovernanceGate,
    RiskDimensions,
    required_controls,
)


@dataclass(frozen=True)
class GovernedCapability:
    profile: CapabilityGovernanceProfile
    expected_mode: str  # allow | shadow | proposal
    rationale: str


def _fully_governed(name: str, level: CapabilityLevel, *, effects=(), risks=None) -> CapabilityGovernanceProfile:
    return CapabilityGovernanceProfile.build(
        name,
        level,
        effects=effects,
        risks=risks,
        controls=required_controls(level, effects=effects, risks=risks),
    )


def current_inventory() -> tuple[GovernedCapability, ...]:
    return (
        GovernedCapability(
            _fully_governed(
                "project.state.read",
                CapabilityLevel.OBSERVE,
                risks=RiskDimensions(authority=0, persistence=2),
            ),
            "allow",
            "read-only State Kernel view",
        ),
        GovernedCapability(
            _fully_governed(
                "project.state.commit",
                CapabilityLevel.COMMIT,
                effects=("canonical_state",),
                risks=RiskDimensions(authority=3, persistence=5, blast_radius=3),
            ),
            "allow",
            "State Kernel CAS/conflict/rollback lineage is present",
        ),
        GovernedCapability(
            _fully_governed(
                "cognitive.synthesis",
                CapabilityLevel.SYNTHESIZE,
                risks=RiskDimensions(authority=1, uncertainty=4, opacity=3),
            ),
            "allow",
            "candidate-only synthesis with provenance/confidence controls",
        ),
        GovernedCapability(
            _fully_governed(
                "cognitive.promote.project",
                CapabilityLevel.COMMIT,
                effects=("durable_memory",),
                risks=RiskDimensions(authority=3, persistence=4, propagation=2, uncertainty=3),
            ),
            "allow",
            "deterministic promotion gate and revocable durable cognition",
        ),
        GovernedCapability(
            _fully_governed(
                "cognitive.promote.cross_project",
                CapabilityLevel.COMMIT,
                effects=("durable_memory", "cross_project"),
                risks=RiskDimensions(authority=3, persistence=5, propagation=5, uncertainty=4),
            ),
            "allow",
            "cross-project promotion requires independent verification and revocation",
        ),
        GovernedCapability(
            _fully_governed(
                "work.continue.select",
                CapabilityLevel.SYNTHESIZE,
                risks=RiskDimensions(authority=1, opacity=2),
            ),
            "allow",
            "selection only; does not execute or mutate ProjectState",
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "browser.gemini.shadow",
                CapabilityLevel.SYNTHESIZE,
                effects=("external_reversible",),
                risks=RiskDimensions(authority=4, blast_radius=2, reversibility=2, uncertainty=4),
                controls=required_controls(CapabilityLevel.SYNTHESIZE),
            ),
            "shadow",
            "browser code exists but live external execution is not authorized until action governance and ledger are wired into the route",
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "node.external.act",
                CapabilityLevel.ACT,
                effects=("external_reversible",),
                risks=RiskDimensions(authority=4, blast_radius=3),
                controls=required_controls(CapabilityLevel.PROPOSE),
            ),
            "proposal",
            "generic node external action remains intentionally unavailable",
        ),
        GovernedCapability(
            CapabilityGovernanceProfile.build(
                "agent.autonomous.external",
                CapabilityLevel.AUTONOMOUS,
                effects=("external_reversible", "autonomous"),
                risks=RiskDimensions(authority=6, blast_radius=5, autonomy=6, persistence=4, propagation=4),
                controls=required_controls(CapabilityLevel.PROPOSE),
            ),
            "proposal",
            "autonomous external action is explicitly not enabled",
        ),
    )


def audit_inventory() -> tuple[str, ...]:
    """Return governance coverage violations; empty means inventory matches policy."""
    errors: list[str] = []
    gate = GovernanceGate()
    seen: set[str] = set()
    for entry in current_inventory():
        profile = entry.profile
        if profile.capability in seen:
            errors.append(f"duplicate capability profile: {profile.capability}")
            continue
        seen.add(profile.capability)
        decision = gate.evaluate(profile)
        if entry.expected_mode == "allow" and not decision.allowed:
            errors.append(f"{profile.capability} expected allow but missing: {','.join(decision.missing_controls)}")
        if entry.expected_mode in {"shadow", "proposal"} and decision.allowed:
            errors.append(f"{profile.capability} unexpectedly has production authority")
    return tuple(errors)

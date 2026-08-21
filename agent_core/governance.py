"""Executable governance gates for AgentOS capability promotion.

Prime law: capability must never scale faster than governance.

This module deliberately stays deterministic. Models and runtimes may describe
or propose a capability, but promotion is decided from explicit risk dimensions
and controls rather than model confidence or prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class CapabilityLevel(IntEnum):
    OBSERVE = 0
    SYNTHESIZE = 1
    PROPOSE = 2
    COMMIT_STATE = 3
    EXTERNAL_REVERSIBLE = 4
    EXTERNAL_HIGH_IMPACT = 5
    AUTONOMOUS_CROSS_PROJECT = 6


# Minimum deterministic controls required before a capability may operate at a
# given level. Higher levels inherit every lower-level requirement.
_LEVEL_CONTROLS: dict[CapabilityLevel, frozenset[str]] = {
    CapabilityLevel.OBSERVE: frozenset({"authentication", "provenance"}),
    CapabilityLevel.SYNTHESIZE: frozenset(
        {"source_tracking", "confidence_state", "contradiction_retention"}
    ),
    CapabilityLevel.PROPOSE: frozenset(
        {"typed_proposal", "validation", "reviewability"}
    ),
    CapabilityLevel.COMMIT_STATE: frozenset(
        {"scoped_principal", "cas_conflict_check", "audit", "rollback"}
    ),
    CapabilityLevel.EXTERNAL_REVERSIBLE: frozenset(
        {"idempotency", "receipt", "bounded_scope", "compensation"}
    ),
    CapabilityLevel.EXTERNAL_HIGH_IMPACT: frozenset(
        {"approval_gate", "circuit_breaker", "least_privilege"}
    ),
    CapabilityLevel.AUTONOMOUS_CROSS_PROJECT: frozenset(
        {
            "continuous_policy",
            "budget_limit",
            "anomaly_detection",
            "revocation",
            "human_override",
            "independent_verification",
        }
    ),
}


@dataclass(frozen=True)
class RiskDimensions:
    """Normalized 0..6 risk signals used to derive a minimum capability level."""

    authority: int = 0
    blast_radius: int = 0
    reversibility: int = 0
    autonomy: int = 0
    persistence: int = 0
    propagation: int = 0
    opacity: int = 0
    uncertainty: int = 0

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 6:
                raise ValueError(f"{name} must be an integer from 0 to 6")

    @property
    def required_level(self) -> CapabilityLevel:
        return CapabilityLevel(max(self.__dict__.values(), default=0))


@dataclass(frozen=True)
class CapabilityGovernanceProfile:
    capability: str
    declared_level: CapabilityLevel
    risks: RiskDimensions
    controls: frozenset[str] = field(default_factory=frozenset)
    experimental: bool = True

    @classmethod
    def build(
        cls,
        capability: str,
        declared_level: CapabilityLevel | int,
        *,
        risks: RiskDimensions | None = None,
        controls: Iterable[str] = (),
        experimental: bool = True,
    ) -> "CapabilityGovernanceProfile":
        capability = str(capability or "").strip()
        if not capability:
            raise ValueError("capability is required")
        return cls(
            capability=capability,
            declared_level=CapabilityLevel(declared_level),
            risks=risks or RiskDimensions(),
            controls=frozenset(str(item).strip() for item in controls if str(item).strip()),
            experimental=bool(experimental),
        )


@dataclass(frozen=True)
class GovernanceDecision:
    allowed: bool
    capability: str
    requested_level: CapabilityLevel
    required_level: CapabilityLevel
    effective_level: CapabilityLevel
    missing_controls: tuple[str, ...]
    degraded_to: str | None
    reason: str


def required_controls(level: CapabilityLevel | int) -> frozenset[str]:
    level = CapabilityLevel(level)
    controls: set[str] = set()
    for candidate in CapabilityLevel:
        if candidate <= level:
            controls.update(_LEVEL_CONTROLS[candidate])
    return frozenset(controls)


class GovernanceGate:
    """Fail-closed promotion checker.

    Missing governance never increases authority. When requested operation is
    above synthesis/proposal and controls are incomplete, callers are told to
    degrade to proposal/read-only rather than execute the higher authority.
    """

    def evaluate(
        self,
        profile: CapabilityGovernanceProfile,
        *,
        requested_level: CapabilityLevel | int | None = None,
    ) -> GovernanceDecision:
        requested = CapabilityLevel(
            profile.declared_level if requested_level is None else requested_level
        )
        required_level = max(profile.declared_level, profile.risks.required_level)
        effective_required = max(required_level, requested)
        missing = tuple(sorted(required_controls(effective_required) - profile.controls))

        if requested < required_level:
            return GovernanceDecision(
                allowed=False,
                capability=profile.capability,
                requested_level=requested,
                required_level=required_level,
                effective_level=CapabilityLevel.OBSERVE,
                missing_controls=missing,
                degraded_to="read_only",
                reason="declared/requested authority is lower than the capability risk profile",
            )

        if missing:
            degraded = "proposal" if requested >= CapabilityLevel.COMMIT_STATE else "read_only"
            effective = (
                CapabilityLevel.PROPOSE
                if degraded == "proposal"
                else CapabilityLevel.OBSERVE
            )
            return GovernanceDecision(
                allowed=False,
                capability=profile.capability,
                requested_level=requested,
                required_level=required_level,
                effective_level=effective,
                missing_controls=missing,
                degraded_to=degraded,
                reason="required governance controls are incomplete; fail closed",
            )

        return GovernanceDecision(
            allowed=True,
            capability=profile.capability,
            requested_level=requested,
            required_level=required_level,
            effective_level=requested,
            missing_controls=(),
            degraded_to=None,
            reason="capability and governance controls are aligned",
        )

    def require(
        self,
        profile: CapabilityGovernanceProfile,
        *,
        requested_level: CapabilityLevel | int | None = None,
    ) -> GovernanceDecision:
        decision = self.evaluate(profile, requested_level=requested_level)
        if not decision.allowed:
            missing = ", ".join(decision.missing_controls) or "risk/authority alignment"
            raise PermissionError(
                f"governance gate denied {profile.capability}: {decision.reason}; missing={missing}"
            )
        return decision

"""Executable governance gates for AgentOS capability promotion.

Prime law: capability must never scale faster than governance.

Governance strength is monotonic, but controls are effect-aware. A powerful
cognitive capability must gain stronger cognitive governance; it should not be
forced to satisfy unrelated external-side-effect controls merely because its
knowledge can propagate widely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class CapabilityLevel(IntEnum):
    OBSERVE = 0
    SYNTHESIZE = 1
    PROPOSE = 2
    COMMIT = 3
    ACT = 4
    HIGH_IMPACT = 5
    AUTONOMOUS = 6


_LEVEL_CONTROLS: dict[CapabilityLevel, frozenset[str]] = {
    CapabilityLevel.OBSERVE: frozenset({"authentication", "provenance"}),
    CapabilityLevel.SYNTHESIZE: frozenset(
        {"source_tracking", "confidence_state", "contradiction_retention"}
    ),
    CapabilityLevel.PROPOSE: frozenset({"typed_proposal", "validation", "reviewability"}),
    CapabilityLevel.COMMIT: frozenset({"audit", "scoped_principal"}),
    CapabilityLevel.ACT: frozenset({"bounded_scope", "receipt"}),
    CapabilityLevel.HIGH_IMPACT: frozenset({"least_privilege", "circuit_breaker"}),
    CapabilityLevel.AUTONOMOUS: frozenset(
        {"continuous_policy", "budget_limit", "anomaly_detection", "human_override", "revocation"}
    ),
}

_EFFECT_CONTROLS: dict[str, frozenset[str]] = {
    "canonical_state": frozenset({"cas_conflict_check", "rollback", "audit"}),
    "durable_memory": frozenset(
        {"source_tracking", "confidence_state", "contradiction_retention", "revocation"}
    ),
    "cross_project": frozenset({"independent_verification", "revocation"}),
    "external_reversible": frozenset({"idempotency", "receipt", "compensation", "bounded_scope"}),
    "external_high_impact": frozenset(
        {"approval_gate", "least_privilege", "circuit_breaker", "receipt"}
    ),
    "autonomous": frozenset(
        {"continuous_policy", "budget_limit", "anomaly_detection", "human_override", "revocation"}
    ),
}


@dataclass(frozen=True)
class RiskDimensions:
    """Normalized 0..6 signals; each raises relevant controls, not unrelated ones."""

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
        # Authority/autonomy determine minimum operating strength. Other risk
        # dimensions add controls without pretending to be capability classes.
        return CapabilityLevel(max(self.authority, self.autonomy))

    def extra_controls(self) -> frozenset[str]:
        controls: set[str] = set()
        if self.blast_radius >= 3:
            controls.add("bounded_scope")
        if self.blast_radius >= 5:
            controls.add("circuit_breaker")
        if self.reversibility >= 4:
            controls.add("compensation")
        if self.autonomy >= 3:
            controls.add("continuous_policy")
        if self.autonomy >= 5:
            controls.update({"human_override", "revocation"})
        if self.persistence >= 3:
            controls.add("audit")
        if self.persistence >= 4:
            controls.add("revocation")
        if self.propagation >= 3:
            controls.add("contradiction_retention")
        if self.propagation >= 4:
            controls.add("independent_verification")
        if self.opacity >= 3:
            controls.add("explanation")
        if self.uncertainty >= 3:
            controls.add("confidence_state")
        if self.uncertainty >= 5:
            controls.add("independent_verification")
        return frozenset(controls)


@dataclass(frozen=True)
class CapabilityGovernanceProfile:
    capability: str
    declared_level: CapabilityLevel
    risks: RiskDimensions
    effects: frozenset[str] = field(default_factory=frozenset)
    controls: frozenset[str] = field(default_factory=frozenset)
    experimental: bool = True

    @classmethod
    def build(
        cls,
        capability: str,
        declared_level: CapabilityLevel | int,
        *,
        risks: RiskDimensions | None = None,
        effects: Iterable[str] = (),
        controls: Iterable[str] = (),
        experimental: bool = True,
    ) -> "CapabilityGovernanceProfile":
        capability = str(capability or "").strip()
        if not capability:
            raise ValueError("capability is required")
        normalized_effects = frozenset(str(item).strip() for item in effects if str(item).strip())
        unknown = normalized_effects - _EFFECT_CONTROLS.keys()
        if unknown:
            raise ValueError(f"unknown governance effects: {', '.join(sorted(unknown))}")
        return cls(
            capability=capability,
            declared_level=CapabilityLevel(declared_level),
            risks=risks or RiskDimensions(),
            effects=normalized_effects,
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


def level_controls(level: CapabilityLevel | int) -> frozenset[str]:
    level = CapabilityLevel(level)
    controls: set[str] = set()
    for candidate in CapabilityLevel:
        if candidate <= level:
            controls.update(_LEVEL_CONTROLS[candidate])
    return frozenset(controls)


def required_controls(
    level: CapabilityLevel | int,
    *,
    effects: Iterable[str] = (),
    risks: RiskDimensions | None = None,
) -> frozenset[str]:
    controls = set(level_controls(level))
    for effect in effects:
        if effect not in _EFFECT_CONTROLS:
            raise ValueError(f"unknown governance effect: {effect}")
        controls.update(_EFFECT_CONTROLS[effect])
    if risks is not None:
        controls.update(risks.extra_controls())
    return frozenset(controls)


class GovernanceGate:
    """Deterministic, fail-closed promotion checker."""

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
        controls_needed = required_controls(
            max(required_level, requested), effects=profile.effects, risks=profile.risks
        )
        missing = tuple(sorted(controls_needed - profile.controls))

        if requested < required_level:
            return GovernanceDecision(
                allowed=False,
                capability=profile.capability,
                requested_level=requested,
                required_level=required_level,
                effective_level=CapabilityLevel.OBSERVE,
                missing_controls=missing,
                degraded_to="read_only",
                reason="requested authority is below the capability risk requirement",
            )

        if missing:
            degraded = "proposal" if requested >= CapabilityLevel.COMMIT else "read_only"
            effective = CapabilityLevel.PROPOSE if degraded == "proposal" else CapabilityLevel.OBSERVE
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

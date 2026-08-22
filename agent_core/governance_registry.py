"""Authoritative registry of AgentOS capability governance profiles.

Untrusted runtimes/providers/nodes may name a capability, but they may not
supply their own governance controls. Authorization resolves profiles from this
registry only.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel


@dataclass(frozen=True)
class RegistryChange:
    capability: str
    actor_ref: str
    previous_level: CapabilityLevel | None
    new_level: CapabilityLevel
    owner_approved: bool
    reason: str


def _risk_tuple(profile: CapabilityGovernanceProfile) -> tuple[int, ...]:
    r = profile.risks
    return (
        r.authority,
        r.blast_radius,
        r.reversibility,
        r.autonomy,
        r.persistence,
        r.propagation,
        r.opacity,
        r.uncertainty,
    )


def _is_relaxation(old: CapabilityGovernanceProfile, new: CapabilityGovernanceProfile) -> bool:
    if new.declared_level > old.declared_level:
        return True
    if not old.controls <= new.controls:  # removing a control
        return True
    if not old.effects <= new.effects:  # hiding/removing an effect classification
        return True
    old_risk = _risk_tuple(old)
    new_risk = _risk_tuple(new)
    if any(new_value < old_value for old_value, new_value in zip(old_risk, new_risk)):
        return True
    return False


class GovernanceRegistry:
    def __init__(self, profiles: tuple[CapabilityGovernanceProfile, ...] = ()) -> None:
        self._profiles: dict[str, CapabilityGovernanceProfile] = {}
        self._changes: list[RegistryChange] = []
        for profile in profiles:
            if profile.capability in self._profiles:
                raise ValueError(f"duplicate capability profile: {profile.capability}")
            self._profiles[profile.capability] = profile

    def get(self, capability: str) -> CapabilityGovernanceProfile | None:
        return self._profiles.get(capability)

    def profiles(self) -> tuple[CapabilityGovernanceProfile, ...]:
        return tuple(self._profiles[name] for name in sorted(self._profiles))

    def changes(self) -> tuple[RegistryChange, ...]:
        return tuple(self._changes)

    def replace(
        self,
        profile: CapabilityGovernanceProfile,
        *,
        actor_ref: str,
        reason: str,
        owner_approved: bool = False,
    ) -> None:
        if not actor_ref.strip() or not reason.strip():
            raise ValueError("actor_ref and reason are required")
        old = self._profiles.get(profile.capability)
        if old is None:
            if not owner_approved:
                raise PermissionError("new capability authority requires owner-approved registration")
        elif _is_relaxation(old, profile) and not owner_approved:
            raise PermissionError("governance relaxation requires owner approval")

        self._profiles[profile.capability] = profile
        self._changes.append(
            RegistryChange(
                capability=profile.capability,
                actor_ref=actor_ref,
                previous_level=old.declared_level if old else None,
                new_level=profile.declared_level,
                owner_approved=owner_approved,
                reason=reason,
            )
        )

"""Bounded governance learning from safety outcomes.

Governance may automatically become more conservative. Any relaxation that
would increase capability authority still requires explicit owner approval.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel
from runtime_core.governance_experience import GovernanceExperience


@dataclass(frozen=True)
class GovernanceAdjustment:
    capability: str
    add_controls: tuple[str, ...]
    new_max_level: CapabilityLevel
    requires_owner_approval: bool
    reason: str


def propose_adjustment(
    profile: CapabilityGovernanceProfile,
    experience: GovernanceExperience,
) -> GovernanceAdjustment:
    if profile.capability != experience.capability:
        raise ValueError("experience/profile capability mismatch")

    proposed_level = profile.declared_level
    if experience.proposed_max_level is not None:
        proposed_level = CapabilityLevel(experience.proposed_max_level)

    # Lower/equal authority and additional controls are conservative changes.
    # Any request to raise authority is a privilege expansion.
    requires_owner = proposed_level > profile.declared_level
    controls = tuple(sorted(set(experience.proposed_controls) - set(profile.controls)))
    return GovernanceAdjustment(
        capability=profile.capability,
        add_controls=controls,
        new_max_level=proposed_level,
        requires_owner_approval=requires_owner,
        reason=f"{experience.kind}: {experience.summary}",
    )


def apply_adjustment(
    profile: CapabilityGovernanceProfile,
    adjustment: GovernanceAdjustment,
    *,
    owner_approved: bool = False,
) -> CapabilityGovernanceProfile:
    if adjustment.capability != profile.capability:
        raise ValueError("adjustment/profile capability mismatch")
    if adjustment.requires_owner_approval and not owner_approved:
        raise PermissionError("governance cannot self-expand authority")

    return CapabilityGovernanceProfile.build(
        profile.capability,
        adjustment.new_max_level,
        risks=profile.risks,
        effects=profile.effects,
        controls=set(profile.controls) | set(adjustment.add_controls),
        experimental=profile.experimental,
    )

from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel, required_controls
from agent_core.governance_learning import apply_adjustment, propose_adjustment
from runtime_core.governance_experience import GovernanceExperience


def base_profile(level=CapabilityLevel.ACT):
    effects = ("external_reversible",)
    return CapabilityGovernanceProfile.build(
        "home.light.set",
        level,
        effects=effects,
        controls=required_controls(level, effects=effects),
    )


def test_near_miss_can_add_control_and_reduce_authority_without_owner_approval():
    profile = base_profile()
    experience = GovernanceExperience(
        capability="home.light.set",
        kind="near_miss",
        severity=4,
        summary="unexpected repeated toggle pattern",
        proposed_controls=("rate_limit",),
        proposed_max_level=2,
    )
    adjustment = propose_adjustment(profile, experience)
    assert adjustment.requires_owner_approval is False
    tightened = apply_adjustment(profile, adjustment)
    assert tightened.declared_level == CapabilityLevel.PROPOSE
    assert "rate_limit" in tightened.controls


def test_governance_learning_cannot_raise_its_own_authority():
    profile = base_profile(CapabilityLevel.PROPOSE)
    experience = GovernanceExperience(
        capability="home.light.set",
        kind="successful_intervention",
        severity=1,
        summary="many successful dry runs",
        proposed_max_level=4,
    )
    adjustment = propose_adjustment(profile, experience)
    assert adjustment.requires_owner_approval is True
    try:
        apply_adjustment(profile, adjustment)
    except PermissionError as exc:
        assert "self-expand" in str(exc)
    else:
        raise AssertionError("governance must not grant itself more authority")


def test_owner_can_explicitly_approve_authority_increase_after_review():
    profile = base_profile(CapabilityLevel.PROPOSE)
    experience = GovernanceExperience(
        capability="home.light.set",
        kind="successful_intervention",
        severity=1,
        summary="reviewed evidence supports promotion",
        proposed_max_level=4,
    )
    adjustment = propose_adjustment(profile, experience)
    promoted = apply_adjustment(profile, adjustment, owner_approved=True)
    assert promoted.declared_level == CapabilityLevel.ACT

from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel, RiskDimensions, required_controls
from agent_core.governance_registry import GovernanceRegistry


def profile(level=CapabilityLevel.PROPOSE, *, controls=None, effects=(), risks=None):
    if controls is None:
        controls = required_controls(level, effects=effects, risks=risks)
    return CapabilityGovernanceProfile.build(
        "cap.test",
        level,
        effects=effects,
        risks=risks,
        controls=controls,
    )


def test_new_capability_registration_requires_owner_approval():
    registry = GovernanceRegistry()
    try:
        registry.replace(profile(), actor_ref="agent:self", reason="self register")
    except PermissionError as exc:
        assert "owner-approved" in str(exc)
    else:
        raise AssertionError("runtime must not self-register authority")

    registry.replace(
        profile(),
        actor_ref="owner:alston",
        reason="explicit bootstrap",
        owner_approved=True,
    )
    assert registry.get("cap.test") is not None


def test_adding_controls_or_increasing_risk_is_conservative_and_can_be_automatic():
    initial = profile(risks=RiskDimensions(authority=2))
    registry = GovernanceRegistry((initial,))
    tightened = CapabilityGovernanceProfile.build(
        "cap.test",
        CapabilityLevel.PROPOSE,
        risks=RiskDimensions(authority=2, uncertainty=4),
        controls=set(initial.controls) | {"extra_guard", "confidence_state"},
    )
    registry.replace(
        tightened,
        actor_ref="governance:learner",
        reason="near miss",
    )
    assert "extra_guard" in registry.get("cap.test").controls


def test_removing_control_requires_owner_approval():
    initial = profile(controls=set(required_controls(CapabilityLevel.PROPOSE)) | {"rate_limit"})
    registry = GovernanceRegistry((initial,))
    relaxed = profile(controls=required_controls(CapabilityLevel.PROPOSE))
    try:
        registry.replace(relaxed, actor_ref="governance:learner", reason="seems stable")
    except PermissionError as exc:
        assert "relaxation" in str(exc)
    else:
        raise AssertionError("automatic governance must not remove controls")


def test_lowering_risk_classification_requires_owner_approval():
    initial = profile(risks=RiskDimensions(authority=2, uncertainty=5), controls=required_controls(CapabilityLevel.PROPOSE, risks=RiskDimensions(authority=2, uncertainty=5)))
    registry = GovernanceRegistry((initial,))
    lowered = profile(risks=RiskDimensions(authority=2, uncertainty=1), controls=initial.controls)
    try:
        registry.replace(lowered, actor_ref="agent:self", reason="claim lower risk")
    except PermissionError as exc:
        assert "relaxation" in str(exc)
    else:
        raise AssertionError("runtime must not lower its own risk classification")

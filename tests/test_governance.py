from agent_core.governance import (
    CapabilityGovernanceProfile,
    CapabilityLevel,
    GovernanceGate,
    RiskDimensions,
    required_controls,
)


def profile(level, *, risks=None, controls=()):
    return CapabilityGovernanceProfile.build(
        "cognitive.synthesis",
        level,
        risks=risks,
        controls=controls,
    )


def test_level_controls_are_monotonic():
    previous = frozenset()
    for level in CapabilityLevel:
        current = required_controls(level)
        assert previous <= current
        previous = current


def test_synthesis_requires_provenance_confidence_and_contradictions():
    controls = required_controls(CapabilityLevel.SYNTHESIZE)
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.SYNTHESIZE, controls=controls)
    )
    assert decision.allowed is True
    assert decision.effective_level == CapabilityLevel.SYNTHESIZE


def test_missing_control_fails_closed():
    controls = required_controls(CapabilityLevel.COMMIT_STATE) - {"rollback"}
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.COMMIT_STATE, controls=controls)
    )
    assert decision.allowed is False
    assert decision.degraded_to == "proposal"
    assert decision.effective_level == CapabilityLevel.PROPOSE
    assert "rollback" in decision.missing_controls


def test_high_risk_dimensions_raise_required_governance():
    risks = RiskDimensions(
        authority=2,
        blast_radius=5,
        reversibility=5,
        autonomy=2,
        persistence=3,
        propagation=4,
    )
    controls = required_controls(CapabilityLevel.PROPOSE)
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.PROPOSE, risks=risks, controls=controls)
    )
    assert decision.allowed is False
    assert decision.required_level == CapabilityLevel.EXTERNAL_HIGH_IMPACT


def test_high_impact_action_requires_all_inherited_controls():
    level = CapabilityLevel.EXTERNAL_HIGH_IMPACT
    controls = required_controls(level)
    decision = GovernanceGate().evaluate(profile(level, controls=controls))
    assert decision.allowed is True
    assert "approval_gate" in controls
    assert "compensation" in controls
    assert "rollback" in controls
    assert "provenance" in controls


def test_autonomous_cross_project_requires_independent_verification_and_override():
    level = CapabilityLevel.AUTONOMOUS_CROSS_PROJECT
    controls = required_controls(level) - {"independent_verification", "human_override"}
    decision = GovernanceGate().evaluate(profile(level, controls=controls))
    assert decision.allowed is False
    assert decision.degraded_to == "proposal"
    assert set(decision.missing_controls) == {
        "human_override",
        "independent_verification",
    }


def test_require_raises_when_governance_is_incomplete():
    try:
        GovernanceGate().require(profile(CapabilityLevel.COMMIT_STATE))
    except PermissionError as exc:
        assert "fail closed" in str(exc)
    else:
        raise AssertionError("expected governance gate denial")


def test_invalid_risk_dimension_is_rejected():
    try:
        RiskDimensions(autonomy=7)
    except ValueError as exc:
        assert "autonomy" in str(exc)
    else:
        raise AssertionError("expected invalid risk dimension rejection")

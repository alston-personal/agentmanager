from agent_core.governance import (
    CapabilityGovernanceProfile,
    CapabilityLevel,
    GovernanceGate,
    RiskDimensions,
    effect_minimum_level,
    required_controls,
)


def profile(level, *, risks=None, effects=(), controls=()):
    return CapabilityGovernanceProfile.build(
        "cognitive.synthesis",
        level,
        risks=risks,
        effects=effects,
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


def test_canonical_state_commit_requires_state_specific_controls():
    effects = {"canonical_state"}
    controls = required_controls(CapabilityLevel.COMMIT, effects=effects) - {"rollback"}
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.COMMIT, effects=effects, controls=controls)
    )
    assert decision.allowed is False
    assert decision.degraded_to == "proposal"
    assert decision.effective_level == CapabilityLevel.PROPOSE
    assert "rollback" in decision.missing_controls


def test_cross_project_durable_cognition_is_commit_level_but_not_external_action():
    risks = RiskDimensions(authority=3, persistence=4, propagation=5, uncertainty=3)
    effects = {"durable_memory", "cross_project"}
    controls = required_controls(
        CapabilityLevel.COMMIT, effects=effects, risks=risks
    )
    decision = GovernanceGate().evaluate(
        profile(
            CapabilityLevel.COMMIT,
            risks=risks,
            effects=effects,
            controls=controls,
        )
    )
    assert decision.allowed is True
    assert decision.required_level == CapabilityLevel.COMMIT
    assert "independent_verification" in controls
    assert "revocation" in controls
    assert "compensation" not in controls
    assert "idempotency" not in controls
    assert "approval_gate" not in controls


def test_external_reversible_action_requires_act_level_and_side_effect_controls():
    effects = {"external_reversible"}
    assert effect_minimum_level(effects) == CapabilityLevel.ACT
    underdeclared = profile(
        CapabilityLevel.SYNTHESIZE,
        effects=effects,
        controls=required_controls(CapabilityLevel.ACT, effects=effects),
    )
    denied = GovernanceGate().evaluate(underdeclared)
    assert denied.allowed is False
    assert denied.required_level == CapabilityLevel.ACT

    controls = required_controls(CapabilityLevel.ACT, effects=effects)
    allowed = GovernanceGate().evaluate(
        profile(CapabilityLevel.ACT, effects=effects, controls=controls)
    )
    assert allowed.allowed is True
    assert "compensation" in controls
    assert "idempotency" in controls
    assert "receipt" in controls
    assert "side_effect_ledger" in controls


def test_high_impact_external_action_requires_level_five_and_approval_gate():
    effects = {"external_high_impact"}
    controls = required_controls(CapabilityLevel.HIGH_IMPACT, effects=effects) - {"approval_gate"}
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.HIGH_IMPACT, effects=effects, controls=controls)
    )
    assert decision.allowed is False
    assert decision.required_level == CapabilityLevel.HIGH_IMPACT
    assert "approval_gate" in decision.missing_controls


def test_autonomous_effect_cannot_be_underdeclared():
    effects = {"autonomous"}
    controls = required_controls(CapabilityLevel.AUTONOMOUS, effects=effects)
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.PROPOSE, effects=effects, controls=controls)
    )
    assert decision.allowed is False
    assert decision.required_level == CapabilityLevel.AUTONOMOUS


def test_autonomy_risk_raises_minimum_operating_level():
    risks = RiskDimensions(authority=2, autonomy=5)
    controls = required_controls(CapabilityLevel.HIGH_IMPACT, risks=risks)
    decision = GovernanceGate().evaluate(
        profile(CapabilityLevel.PROPOSE, risks=risks, controls=controls)
    )
    assert decision.allowed is False
    assert decision.required_level == CapabilityLevel.HIGH_IMPACT


def test_require_raises_when_governance_is_incomplete():
    try:
        GovernanceGate().require(
            profile(CapabilityLevel.COMMIT, effects={"canonical_state"})
        )
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


def test_unknown_effect_is_rejected():
    try:
        profile(CapabilityLevel.PROPOSE, effects={"magic"})
    except ValueError as exc:
        assert "magic" in str(exc)
    else:
        raise AssertionError("expected unknown effect rejection")

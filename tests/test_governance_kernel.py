from agent_core.action_authorization import ActionAuthorizationGate
from agent_core.governance import (
    CapabilityGovernanceProfile,
    CapabilityLevel,
    GovernanceGate,
    RiskDimensions,
    governance_change_allowed,
    required_controls,
)
from agent_core.governance_registry import GovernanceRegistry
from agent_core.side_effect_ledger import InMemorySideEffectLedger
from runtime_core.governance_v1 import ActionIntent, ApprovalGrant


def profile(*, capability="home.light.set", level=CapabilityLevel.ACT, effects=("external_reversible",), risks=None, controls=None):
    if controls is None:
        controls = required_controls(level, effects=effects, risks=risks)
    return CapabilityGovernanceProfile.build(
        capability,
        level,
        risks=risks,
        effects=effects,
        controls=controls,
    )


def gate_for(*profiles):
    return ActionAuthorizationGate(GovernanceRegistry(tuple(profiles)))


def intent(*, capability="home.light.set", level=4, key="k1", operation="set:on"):
    return ActionIntent(
        realm_id="realm-alston",
        project_id="home",
        actor_ref="agent:test",
        capability=capability,
        target_ref="device:living-room-light",
        operation=operation,
        requested_level=level,
        idempotency_key=key,
    )


def test_unknown_capability_fails_closed_at_action_boundary():
    authorization = gate_for().evaluate(intent=intent())
    assert authorization.allowed is False
    assert "unknown capability" in authorization.reason


def test_missing_external_controls_fail_closed_and_include_side_effect_ledger():
    p = profile(controls={"authentication", "provenance"})
    decision = GovernanceGate().evaluate(p)
    assert decision.allowed is False
    assert "side_effect_ledger" in decision.missing_controls


def test_complete_reversible_action_can_be_intent_authorized():
    p = profile()
    authorization = gate_for(p).evaluate(intent=intent())
    assert authorization.allowed is True
    assert authorization.effective_level == CapabilityLevel.ACT


def test_high_impact_requires_intent_bound_approval():
    effects = ("external_reversible", "external_high_impact")
    controls = required_controls(CapabilityLevel.HIGH_IMPACT, effects=effects)
    p = profile(
        capability="home.lock.unlock",
        level=CapabilityLevel.HIGH_IMPACT,
        effects=effects,
        controls=controls,
    )
    i = intent(capability="home.lock.unlock", level=5)
    gate = gate_for(p)
    pending = gate.evaluate(intent=i)
    assert pending.allowed is False
    assert "approval" in pending.reason

    wrong = ApprovalGrant(intent_id="intent_wrong", approver_ref="owner:alston", scope="home.lock.unlock")
    assert gate.evaluate(intent=i, approval=wrong).allowed is False

    approval = ApprovalGrant(intent_id=i.intent_id, approver_ref="owner:alston", scope="home.lock.unlock", grant_id="approval:1")
    allowed = gate.evaluate(intent=i, approval=approval)
    assert allowed.allowed is True
    assert allowed.approval_ref == "approval:1"


def test_requested_authority_cannot_exceed_registry_profile():
    p = profile(
        level=CapabilityLevel.PROPOSE,
        effects=(),
        controls=required_controls(CapabilityLevel.PROPOSE),
    )
    authorization = gate_for(p).evaluate(intent=intent(level=4))
    assert authorization.allowed is False
    assert "exceeds" in authorization.reason


def test_governance_can_self_tighten_but_not_self_expand_authority():
    assert governance_change_allowed(old_level=5, new_level=4, owner_approved=False)
    assert governance_change_allowed(old_level=4, new_level=4, owner_approved=False)
    assert not governance_change_allowed(old_level=4, new_level=5, owner_approved=False)
    assert governance_change_allowed(old_level=4, new_level=5, owner_approved=True)


def test_autonomous_risk_requires_stronger_governance_before_authorization():
    risks = RiskDimensions(authority=2, autonomy=6, blast_radius=5)
    p = profile(
        capability="agent.autonomous.act",
        level=CapabilityLevel.PROPOSE,
        effects=(),
        risks=risks,
        controls=required_controls(CapabilityLevel.AUTONOMOUS, risks=risks),
    )
    authorization = gate_for(p).evaluate(
        intent=intent(capability="agent.autonomous.act", level=2),
    )
    assert authorization.allowed is False


def test_side_effect_requires_intent_bound_authorization():
    ledger = InMemorySideEffectLedger()
    i = intent()
    p = profile()
    auth = gate_for(p).evaluate(intent=i)
    other = intent(key="k2", operation="set:off")
    try:
        ledger.prepare(intent=other, authorization=auth, kind="device", target="light")
    except ValueError as exc:
        assert "does not bind" in str(exc)
    else:
        raise AssertionError("authorization for another intent must not prepare side effect")


def test_side_effect_ledger_is_idempotent_receipted_and_compensatable():
    p = profile()
    i = intent(key="same-request")
    auth = gate_for(p).evaluate(intent=i)
    ledger = InMemorySideEffectLedger()
    first = ledger.prepare(
        intent=i,
        authorization=auth,
        kind="home.light.set",
        target="device:living-room-light",
        compensation_ref="restore:previous-light-state",
    )
    second = ledger.prepare(
        intent=i,
        authorization=auth,
        kind="home.light.set",
        target="device:living-room-light",
        compensation_ref="restore:previous-light-state",
    )
    assert first.side_effect_id == second.side_effect_id
    committed = ledger.commit(first.side_effect_id, receipt_ref="receipt:device-ack-1")
    assert committed.status == "committed"
    compensated = ledger.compensate(first.side_effect_id, receipt_ref="receipt:rollback-1")
    assert compensated.status == "compensated"

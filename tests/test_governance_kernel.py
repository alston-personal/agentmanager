from agent_core.governance_gate import (
    GovernanceGate,
    capability_is_release_ready,
    governance_change_allowed,
    missing_governance,
)
from agent_core.side_effect_ledger import InMemorySideEffectLedger
from runtime_core.governance_v1 import ActionIntent, ApprovalGrant, CapabilityProfile


def profile(*, capability="home.light.set", level=4, risk="medium", external=True, physical=False, reversible=True, controls=()):
    return CapabilityProfile(
        capability=capability,
        level=level,
        risk_band=risk,
        external_effect=external,
        physical_effect=physical,
        reversible=reversible,
        controls=frozenset(controls),
    )


def intent(*, capability="home.light.set", level=4, key="k1"):
    return ActionIntent(
        realm_id="realm-alston",
        project_id="home",
        actor_ref="agent:test",
        capability=capability,
        target_ref="device:living-room-light",
        operation="set:on",
        requested_level=level,
        idempotency_key=key,
    )


def test_unknown_capability_fails_closed():
    decision = GovernanceGate().evaluate(intent=intent(), profile=None)
    assert decision.decision == "deny"
    assert decision.reason == "unknown_capability"


def test_missing_level4_controls_denies_external_action():
    p = profile(controls={"authentication", "provenance"})
    assert not capability_is_release_ready(p)
    assert "side_effect_ledger" in missing_governance(p)
    decision = GovernanceGate().evaluate(intent=intent(), profile=p)
    assert decision.decision == "deny"
    assert "side_effect_ledger" in decision.missing_controls


def test_complete_reversible_level4_action_can_be_allowed_without_high_impact_approval():
    controls = {
        "authentication", "provenance", "scoped_principal", "audit",
        "idempotency", "receipt", "bounded_scope", "compensation",
        "side_effect_ledger",
    }
    p = profile(controls=controls)
    decision = GovernanceGate().evaluate(intent=intent(), profile=p)
    assert decision.decision == "allow"
    assert decision.effective_level == 4


def test_high_risk_or_physical_action_requires_bound_approval():
    controls = {
        "authentication", "provenance", "scoped_principal", "audit",
        "idempotency", "receipt", "bounded_scope", "compensation",
        "side_effect_ledger", "approval_gate", "circuit_breaker",
        "minimal_privilege", "physical_safety_policy",
    }
    p = profile(capability="home.lock.unlock", level=5, risk="high", physical=True, controls=controls)
    i = intent(capability="home.lock.unlock", level=5)
    pending = GovernanceGate().evaluate(intent=i, profile=p)
    assert pending.decision == "require_approval"
    approval = ApprovalGrant(intent_id=i.intent_id, approver_ref="owner:alston", scope="home.lock.unlock")
    allowed = GovernanceGate().evaluate(intent=i, profile=p, approval=approval)
    assert allowed.decision == "allow"


def test_requested_authority_cannot_exceed_capability_profile():
    p = profile(level=2, external=False, controls={
        "authentication", "provenance", "typed_proposal", "validation", "reviewability"
    })
    decision = GovernanceGate().evaluate(intent=intent(level=4), profile=p)
    assert decision.decision == "deny"
    assert decision.reason == "requested_authority_exceeds_profile"


def test_governance_can_self_tighten_but_not_self_expand_authority():
    assert governance_change_allowed(old_level=5, new_level=4, owner_approved=False)
    assert governance_change_allowed(old_level=4, new_level=4, owner_approved=False)
    assert not governance_change_allowed(old_level=4, new_level=5, owner_approved=False)
    assert governance_change_allowed(old_level=4, new_level=5, owner_approved=True)


def test_side_effect_requires_governance_allow_and_level_four():
    ledger = InMemorySideEffectLedger()
    i = intent()
    denied = GovernanceGate().evaluate(intent=i, profile=profile(controls=set()))
    try:
        ledger.prepare(intent=i, decision=denied, kind="device", target="light")
    except PermissionError:
        pass
    else:
        raise AssertionError("denied intent must not prepare side effect")


def test_side_effect_ledger_is_idempotent_and_receipted():
    controls = {
        "authentication", "provenance", "scoped_principal", "audit",
        "idempotency", "receipt", "bounded_scope", "compensation", "side_effect_ledger",
    }
    p = profile(controls=controls)
    i = intent(key="same-request")
    decision = GovernanceGate().evaluate(intent=i, profile=p)
    ledger = InMemorySideEffectLedger()
    first = ledger.prepare(
        intent=i,
        decision=decision,
        kind="home.light.set",
        target="device:living-room-light",
        compensation_ref="restore:previous-light-state",
    )
    second = ledger.prepare(
        intent=i,
        decision=decision,
        kind="home.light.set",
        target="device:living-room-light",
        compensation_ref="restore:previous-light-state",
    )
    assert first.side_effect_id == second.side_effect_id
    committed = ledger.commit(first.side_effect_id, receipt_ref="receipt:device-ack-1")
    assert committed.status == "committed"
    compensated = ledger.compensate(first.side_effect_id, receipt_ref="receipt:rollback-1")
    assert compensated.status == "compensated"


def test_cross_realm_capability_is_forbidden_by_default():
    try:
        CapabilityProfile(
            capability="realm.share",
            level=2,
            risk_band="high",
            cross_realm=True,
        )
    except ValueError as exc:
        assert "cross-realm" in str(exc)
    else:
        raise AssertionError("cross-realm authority must require a future explicit federation contract")

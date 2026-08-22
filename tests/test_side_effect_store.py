from agent_core.action_authorization import ActionAuthorizationGate
from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel, required_controls
from agent_core.governance_registry import GovernanceRegistry
from agent_core.side_effect_ledger import InMemorySideEffectLedger
from agent_core.side_effect_store import SideEffectLedgerStore
from runtime_core.governance_v1 import ActionIntent


def governed_action():
    effects = ("external_reversible",)
    profile = CapabilityGovernanceProfile.build(
        "home.light.set",
        CapabilityLevel.ACT,
        effects=effects,
        controls=required_controls(CapabilityLevel.ACT, effects=effects),
    )
    intent = ActionIntent(
        realm_id="realm-alston",
        project_id="home",
        actor_ref="agent:test",
        capability="home.light.set",
        target_ref="device:light",
        operation="set:on",
        requested_level=4,
        idempotency_key="persist-key",
    )
    registry = GovernanceRegistry((profile,))
    auth = ActionAuthorizationGate(registry).evaluate(intent=intent)
    return intent, auth


def test_side_effect_store_persists_current_record_and_append_only_events(tmp_path):
    intent, auth = governed_action()
    ledger = InMemorySideEffectLedger()
    store = SideEffectLedgerStore(tmp_path / "side-effects.sqlite3")

    prepared = ledger.prepare(
        intent=intent,
        authorization=auth,
        kind="home.light.set",
        target="device:light",
        compensation_ref="restore:off",
    )
    store.persist(prepared, event_type="prepared")
    committed = ledger.commit(prepared.side_effect_id, receipt_ref="receipt:on")
    store.persist(committed, event_type="committed")
    compensated = ledger.compensate(prepared.side_effect_id, receipt_ref="receipt:off")
    store.persist(compensated, event_type="compensated")

    restored = store.get(prepared.side_effect_id)
    assert restored is not None
    assert restored.status == "compensated"
    assert store.by_idempotency_key("persist-key").side_effect_id == prepared.side_effect_id
    assert [event["event_type"] for event in store.events(prepared.side_effect_id)] == [
        "prepared", "committed", "compensated"
    ]


def test_store_rejects_idempotency_collision_across_different_effects(tmp_path):
    intent, auth = governed_action()
    ledger = InMemorySideEffectLedger()
    store = SideEffectLedgerStore(tmp_path / "side-effects.sqlite3")
    first = ledger.prepare(
        intent=intent,
        authorization=auth,
        kind="home.light.set",
        target="device:light",
    )
    store.persist(first, event_type="prepared")

    # SQLite UNIQUE(idempotency_key) is the durable last line of defense.
    from dataclasses import replace
    other = replace(first, side_effect_id="sidefx_other", intent_id="intent_other", intent_hash="different")
    try:
        store.persist(other, event_type="prepared")
    except Exception as exc:
        assert "UNIQUE" in str(exc) or "unique" in str(exc).lower()
    else:
        raise AssertionError("durable idempotency collision must fail closed")

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from agent_core.priority_attention import evaluate_priority, promote_to_work, resolve_blocker
from runtime_core.deferred_v1 import DeferredWorkPacket


def packet(**overrides):
    values = dict(
        project_id="agentmanager",
        base_state_id="state_head",
        title="Oracle Gemini Web live setup",
        instruction="Complete Oracle Browser Worker and Gemini Web shadow E2E verification",
        capability="ai.verify.shadow",
        deferred_since="2026-08-22T00:00:00+00:00",
        importance_base=0.85,
        urgency_base=0.30,
        importance_velocity_per_day=0.0,
        urgency_velocity_per_day=0.01,
        status="blocked",
        reason_deferred="user not currently available at Oracle",
        blockers=("user_available_at_oracle",),
        resume_triggers=("I can use Oracle now", "continue Gemini Web"),
        next_actions=(
            "SSH Oracle",
            "prepare isolated browserworker",
            "manual Gemini login",
            "start gemini_web_worker.py",
            "run local semantic smoke test",
            "register gemini-web-shadow",
            "verify AgentOS E2E",
        ),
        safety_constraints=(
            "do not expose Google cookies",
            "do not open port 8785 publicly",
            "do not modify production",
            "do not merge PR #3",
        ),
        source_refs=("conversation:2026-08-22:oracle-gemini",),
        metadata={"acceptance_criteria": ("shadow task returns normalized semantic result",)},
    )
    values.update(overrides)
    return DeferredWorkPacket(**values)


def test_blocked_packet_does_not_resurface_only_because_time_passes():
    item = packet()
    snap = evaluate_priority(item, now=datetime(2026, 9, 22, tzinfo=timezone.utc))
    assert snap.urgency > 0.60
    assert snap.quadrant == "Q1"
    assert snap.readiness == "blocked"
    assert snap.action == "wait"
    assert snap.resurfaced is False


def test_resolving_dependency_changes_readiness_not_urgency():
    item = packet()
    before = evaluate_priority(item, now=datetime(2026, 8, 22, tzinfo=timezone.utc))
    ready = resolve_blocker(item, "user_available_at_oracle")
    after = evaluate_priority(ready, now=datetime(2026, 8, 22, tzinfo=timezone.utc))
    assert ready.status == "ready"
    assert ready.blockers == ()
    assert before.urgency == after.urgency == pytest.approx(0.30)
    assert after.readiness == "ready"


def test_positive_velocity_moves_q2_to_q1_and_resurfaces_when_ready():
    item = packet(status="ready", blockers=())
    snap = evaluate_priority(item, now=datetime(2026, 9, 22, tzinfo=timezone.utc))
    assert snap.initial_quadrant == "Q2"
    assert snap.quadrant == "Q1"
    assert snap.action == "do_now"
    assert snap.resurfaced is True
    assert "priority_quadrant_changed" in snap.resurfacing_reasons


def test_negative_velocity_can_sink_low_value_work():
    item = packet(
        status="ready",
        blockers=(),
        importance_base=0.70,
        urgency_base=0.20,
        importance_velocity_per_day=-0.01,
        urgency_velocity_per_day=0.0,
    )
    snap = evaluate_priority(item, now=datetime(2026, 9, 12, tzinfo=timezone.utc))
    assert snap.importance < 0.60
    assert snap.quadrant == "Q4"
    assert snap.action == "cool"


def test_semantic_trigger_resurfaces_ready_deferred_work_without_faking_urgency():
    item = packet(status="ready", blockers=(), urgency_velocity_per_day=0.0)
    snap = evaluate_priority(
        item,
        now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        semantic_match=True,
    )
    assert snap.urgency == pytest.approx(0.30)
    assert snap.quadrant == "Q2"
    assert snap.resurfaced is True
    assert snap.resurfacing_reasons == ("semantic_trigger",)


def test_priority_values_are_clamped_to_unit_interval():
    item = packet(
        status="ready",
        blockers=(),
        importance_velocity_per_day=1.0,
        urgency_velocity_per_day=-1.0,
    )
    snap = evaluate_priority(item, now=datetime(2026, 8, 24, tzinfo=timezone.utc))
    assert snap.importance == 1.0
    assert snap.urgency == 0.0


def test_blocked_packet_cannot_enter_active_work_graph():
    with pytest.raises(ValueError, match="blocked"):
        promote_to_work(packet())


def test_ready_packet_promotes_with_resume_checkpoint_preserved():
    item = packet(status="ready", blockers=())
    work = promote_to_work(item, priority=85)
    assert work.project_id == "agentmanager"
    assert work.priority == 85
    assert work.metadata["deferred_id"] == item.deferred_id
    assert "manual Gemini login" in work.metadata["next_actions"]
    assert "do not modify production" in work.metadata["safety_constraints"]


def test_deferred_identity_survives_priority_and_lifecycle_changes():
    item = packet()
    changed = replace(
        item,
        importance_base=0.99,
        urgency_base=0.95,
        importance_velocity_per_day=-0.05,
        urgency_velocity_per_day=0.0,
        status="ready",
        blockers=(),
    )
    assert changed.deferred_id == item.deferred_id

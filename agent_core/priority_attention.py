"""Dynamic Eisenhower priority and resurfacing policy for deferred work."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from runtime_core.deferred_v1 import DeferredWorkPacket
from runtime_core.work_v1 import WorkItem


IMPORTANT_THRESHOLD = 0.60
URGENT_THRESHOLD = 0.60


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _quadrant(importance: float, urgency: float) -> str:
    important = importance >= IMPORTANT_THRESHOLD
    urgent = urgency >= URGENT_THRESHOLD
    if important and urgent:
        return "Q1"
    if important:
        return "Q2"
    if urgent:
        return "Q3"
    return "Q4"


@dataclass(frozen=True)
class PrioritySnapshot:
    deferred_id: str
    importance: float
    urgency: float
    quadrant: str
    initial_quadrant: str
    readiness: str
    action: str
    elapsed_days: float
    resurfaced: bool
    resurfacing_reasons: tuple[str, ...]


def evaluate_priority(
    packet: DeferredWorkPacket,
    *,
    now: datetime,
    importance_event_delta: float = 0.0,
    urgency_event_delta: float = 0.0,
    semantic_match: bool = False,
) -> PrioritySnapshot:
    """Evaluate priority lazily; elapsed time does not mutate the packet.

    Time drift changes priority/attention only.  It never changes epistemic
    confidence, ProjectState, or execution authorization.
    """
    start = _parse_time(packet.deferred_since)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed_days = max(0.0, (now - start).total_seconds() / 86400.0)

    importance = _clamp(
        packet.importance_base
        + packet.importance_velocity_per_day * elapsed_days
        + importance_event_delta
    )
    urgency = _clamp(
        packet.urgency_base
        + packet.urgency_velocity_per_day * elapsed_days
        + urgency_event_delta
    )
    initial_quadrant = _quadrant(packet.importance_base, packet.urgency_base)
    quadrant = _quadrant(importance, urgency)

    blocked = packet.status == "blocked" or bool(packet.blockers)
    readiness = "blocked" if blocked else "ready"

    if blocked:
        action = "wait"
    elif quadrant == "Q1":
        action = "do_now"
    elif quadrant == "Q2":
        action = "protect"
    elif quadrant == "Q3":
        action = "delegate"
    else:
        action = "cool"

    reasons: list[str] = []
    if semantic_match:
        reasons.append("semantic_trigger")
    if quadrant != initial_quadrant:
        reasons.append("priority_quadrant_changed")
    if quadrant == "Q1" and initial_quadrant != "Q1":
        reasons.append("became_urgent_and_important")

    # Blocked work may be remembered but should not repeatedly interrupt active work.
    resurfaced = bool(reasons) and readiness == "ready"
    return PrioritySnapshot(
        deferred_id=packet.deferred_id,
        importance=importance,
        urgency=urgency,
        quadrant=quadrant,
        initial_quadrant=initial_quadrant,
        readiness=readiness,
        action=action,
        elapsed_days=elapsed_days,
        resurfaced=resurfaced,
        resurfacing_reasons=tuple(reasons),
    )


def resolve_blocker(packet: DeferredWorkPacket, blocker: str) -> DeferredWorkPacket:
    """Remove one explicit blocker without fabricating urgency."""
    if blocker not in packet.blockers:
        return packet
    remaining = tuple(value for value in packet.blockers if value != blocker)
    status = "ready" if not remaining else "blocked"
    return replace(packet, blockers=remaining, status=status)


def promote_to_work(packet: DeferredWorkPacket, *, priority: int = 0) -> WorkItem:
    """Create active work only from a ready deferred checkpoint."""
    if packet.status == "blocked" or packet.blockers:
        raise ValueError("blocked deferred work cannot be promoted")
    if packet.status in {"promoted", "cancelled"}:
        raise ValueError("terminal deferred work cannot be promoted")
    return WorkItem(
        project_id=packet.project_id,
        base_state_id=packet.base_state_id,
        instruction=packet.instruction,
        capability=packet.capability,
        priority=priority,
        status="pending",
        acceptance_criteria=tuple(packet.metadata.get("acceptance_criteria", ())),
        runtime_policy=dict(packet.metadata.get("runtime_policy", {})),
        provider_policy=dict(packet.metadata.get("provider_policy", {})),
        created_by=f"deferred:{packet.deferred_id}",
        metadata={
            "deferred_id": packet.deferred_id,
            "resume_title": packet.title,
            "next_actions": packet.next_actions,
            "safety_constraints": packet.safety_constraints,
            "source_refs": packet.source_refs,
        },
    )

"""Portable deferred/blocked work checkpoint for AgentOS.

Deferred work is not active Work Graph work.  It preserves enough context to
resume an unfinished intent without searching old conversations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


DEFERRED_SCHEMA = "agentos.deferred/v1"
DEFERRED_STATUSES = frozenset({"deferred", "blocked", "ready", "promoted", "cancelled"})


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class DeferredWorkPacket:
    project_id: str
    base_state_id: str
    title: str
    instruction: str
    capability: str
    deferred_since: str
    importance_base: float
    urgency_base: float
    importance_velocity_per_day: float = 0.0
    urgency_velocity_per_day: float = 0.0
    status: str = "deferred"
    reason_deferred: str = ""
    blockers: tuple[str, ...] = field(default_factory=tuple)
    resume_triggers: tuple[str, ...] = field(default_factory=tuple)
    next_actions: tuple[str, ...] = field(default_factory=tuple)
    safety_constraints: tuple[str, ...] = field(default_factory=tuple)
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = DEFERRED_SCHEMA

    def __post_init__(self) -> None:
        required = (self.project_id, self.base_state_id, self.title, self.instruction, self.capability, self.deferred_since)
        if any(not str(value).strip() for value in required):
            raise ValueError("project/base/title/instruction/capability/deferred_since are required")
        if self.status not in DEFERRED_STATUSES:
            raise ValueError("invalid deferred status")
        for name, value in (("importance_base", self.importance_base), ("urgency_base", self.urgency_base)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("blockers must be unique")
        if self.status == "blocked" and not self.blockers:
            raise ValueError("blocked packet requires at least one blocker")

    def identity_payload(self) -> dict[str, Any]:
        """Stable semantic checkpoint identity; lifecycle/priority drift is excluded."""
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "base_state_id": self.base_state_id,
            "title": self.title,
            "instruction": self.instruction,
            "capability": self.capability,
            "deferred_since": self.deferred_since,
            "reason_deferred": self.reason_deferred,
            "resume_triggers": self.resume_triggers,
            "next_actions": self.next_actions,
            "safety_constraints": self.safety_constraints,
            "source_refs": self.source_refs,
            "metadata": self.metadata,
        }

    @property
    def deferred_id(self) -> str:
        return "deferred_" + sha256(_canonical(self.identity_payload()).encode("utf-8")).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["deferred_id"] = self.deferred_id
        return value

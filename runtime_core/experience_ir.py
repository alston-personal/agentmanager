"""Portable source-neutral experience events for AgentOS Cognitive Kernel.

ExperienceEvent is the ingestion boundary for distributed conversations, tool
runs, IDE work, web agents, GitHub activity, and runtime observations. Vendor
adapters normalize into this IR; Cognitive Kernel logic does not parse vendor
session formats directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


EXPERIENCE_SCHEMA = "agentos.experience/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ExperienceEvent:
    project_id: str
    source_kind: str
    source_ref: str
    actor_kind: str
    event_kind: str
    content: str
    occurred_at: str
    trust_class: str = "unverified"
    conversation_ref: str | None = None
    parent_event_ids: tuple[str, ...] = field(default_factory=tuple)
    artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = EXPERIENCE_SCHEMA

    def __post_init__(self) -> None:
        required = {
            "project_id": self.project_id,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "actor_kind": self.actor_kind,
            "event_kind": self.event_kind,
            "content": self.content,
            "occurred_at": self.occurred_at,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError("missing experience fields: " + ", ".join(sorted(missing)))
        if self.trust_class not in {"unverified", "observed", "verified", "trusted"}:
            raise ValueError("invalid trust_class")

    @property
    def event_id(self) -> str:
        payload = self.to_dict(include_id=False)
        return "exp_" + sha256(_canonical(payload).encode("utf-8")).hexdigest()[:32]

    @property
    def content_hash(self) -> str:
        return sha256(self.content.encode("utf-8")).hexdigest()

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_id:
            value["event_id"] = "exp_" + sha256(_canonical(value).encode("utf-8")).hexdigest()[:32]
        return value


@dataclass(frozen=True)
class ExperienceBatch:
    project_id: str
    events: tuple[ExperienceEvent, ...]
    source_window_ref: str
    schema_version: str = "agentos.experience-batch/v1"

    def __post_init__(self) -> None:
        if not self.project_id or not self.source_window_ref:
            raise ValueError("project_id and source_window_ref are required")
        if any(item.project_id != self.project_id for item in self.events):
            raise ValueError("all events in a batch must share project_id")

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(item.event_id for item in self.events)

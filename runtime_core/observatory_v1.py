"""Portable Cognitive Observatory records for longitudinal AgentOS analysis.

The observatory is descriptive, never authoritative.  It projects existing
knowledge/relation/lifecycle state into content-addressed snapshots and deltas so
cognitive evolution can be inspected, visualized and benchmarked without
changing ProjectState, knowledge confidence or governance authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


OBSERVATORY_SCHEMA = "agentos.cognitive-observatory/v1"
DELTA_SCHEMA = "agentos.cognitive-delta/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, value: dict[str, Any]) -> str:
    return f"{prefix}_{sha256(_canonical(value).encode('utf-8')).hexdigest()[:32]}"


@dataclass(frozen=True)
class CognitiveMetrics:
    knowledge_count: int = 0
    validated_knowledge_count: int = 0
    superseded_knowledge_count: int = 0
    contradiction_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    validated_relation_count: int = 0
    orphan_entity_count: int = 0
    ungrounded_relation_count: int = 0
    stale_derivative_count: int = 0
    archive_memory_count: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative")

    @property
    def validated_knowledge_ratio(self) -> float:
        return 0.0 if self.knowledge_count == 0 else self.validated_knowledge_count / self.knowledge_count

    @property
    def validated_relation_ratio(self) -> float:
        return 0.0 if self.relation_count == 0 else self.validated_relation_count / self.relation_count


@dataclass(frozen=True)
class CognitiveSnapshot:
    project_id: str
    captured_at: str
    trigger_ref: str
    knowledge_ids: tuple[str, ...] = field(default_factory=tuple)
    relation_ids: tuple[str, ...] = field(default_factory=tuple)
    entity_ids: tuple[str, ...] = field(default_factory=tuple)
    archived_knowledge_ids: tuple[str, ...] = field(default_factory=tuple)
    metrics: CognitiveMetrics = field(default_factory=CognitiveMetrics)
    annotations: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = OBSERVATORY_SCHEMA

    def __post_init__(self) -> None:
        if not self.project_id.strip() or not self.captured_at.strip() or not self.trigger_ref.strip():
            raise ValueError("project_id, captured_at and trigger_ref are required")
        for values in (self.knowledge_ids, self.relation_ids, self.entity_ids, self.archived_knowledge_ids):
            if len(set(values)) != len(values):
                raise ValueError("snapshot identifiers must be unique")

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_id:
            value["snapshot_id"] = _id("cogsnap", value)
        return value

    @property
    def snapshot_id(self) -> str:
        return _id("cogsnap", self.to_dict(include_id=False))


@dataclass(frozen=True)
class CognitiveDelta:
    project_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    added_knowledge_ids: tuple[str, ...] = field(default_factory=tuple)
    removed_knowledge_ids: tuple[str, ...] = field(default_factory=tuple)
    added_relation_ids: tuple[str, ...] = field(default_factory=tuple)
    removed_relation_ids: tuple[str, ...] = field(default_factory=tuple)
    newly_archived_knowledge_ids: tuple[str, ...] = field(default_factory=tuple)
    revived_knowledge_ids: tuple[str, ...] = field(default_factory=tuple)
    metric_delta: dict[str, int] = field(default_factory=dict)
    annotations: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = DELTA_SCHEMA

    def __post_init__(self) -> None:
        if not self.project_id.strip() or not self.from_snapshot_id.strip() or not self.to_snapshot_id.strip():
            raise ValueError("project_id and snapshot lineage are required")

    @property
    def delta_id(self) -> str:
        return _id("cogdelta", asdict(self))

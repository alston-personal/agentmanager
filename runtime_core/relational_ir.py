"""Portable relational primitives for the AgentOS Cognitive Kernel.

Files and memories are not fully understood until their relationships are
explicit. This IR keeps stable entity identity separate from immutable,
provenance-bearing relation claims so aliases, projects, artifacts and derived
works can be connected without turning those links into canonical ProjectState.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


ENTITY_SCHEMA = "agentos.entity/v1"
RELATION_SCHEMA = "agentos.relation/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}_{sha256(_canonical(payload).encode('utf-8')).hexdigest()[:32]}"


def normalize_alias(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


@dataclass(frozen=True)
class EntityRecord:
    """Stable identity projection for a project, artifact, work, concept or event."""

    entity_id: str
    kind: str
    canonical_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    refs: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ENTITY_SCHEMA

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.kind.strip() or not self.canonical_name.strip():
            raise ValueError("entity_id, kind and canonical_name are required")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("entity aliases must be unique")

    @property
    def search_names(self) -> frozenset[str]:
        return frozenset(
            normalize_alias(item)
            for item in (self.canonical_name, *self.aliases, *self.refs)
            if normalize_alias(item)
        )


@dataclass(frozen=True)
class RelationEvidence:
    source_kind: str
    source_ref: str
    content_hash: str
    trust_class: str = "observed"

    def __post_init__(self) -> None:
        if not self.source_kind.strip() or not self.source_ref.strip() or not self.content_hash.strip():
            raise ValueError("relation evidence source_kind, source_ref and content_hash are required")


@dataclass(frozen=True)
class RelationRecord:
    """Immutable claim that one known entity is related to another."""

    subject_id: str
    predicate: str
    object_id: str
    evidence: tuple[RelationEvidence, ...] = field(default_factory=tuple)
    confidence: float = 0.5
    status: str = "candidate"  # candidate|validated|superseded|rejected
    valid_from: str | None = None
    valid_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RELATION_SCHEMA

    def __post_init__(self) -> None:
        if not self.subject_id.strip() or not self.object_id.strip() or not self.predicate.strip():
            raise ValueError("relation subject_id, predicate and object_id are required")
        if self.subject_id == self.object_id and self.predicate not in {"alias_of", "same_as"}:
            raise ValueError("self relation requires alias_of or same_as")
        if self.status not in {"candidate", "validated", "superseded", "rejected"}:
            raise ValueError("invalid relation status")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("relation confidence must be between 0 and 1")

    @property
    def relation_id(self) -> str:
        return _id("rel", self.to_dict(include_id=False))

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_id:
            value["relation_id"] = _id("rel", value)
        return value

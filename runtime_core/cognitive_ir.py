"""Portable primitives for AgentOS Cognitive Kernel.

These objects represent candidate knowledge and synthesis, not canonical project
truth. They are content-addressed, provenance-bearing, and contradiction-aware
so later inputs can re-synthesize earlier conclusions without erasing history.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from hashlib import sha256
import json
from typing import Any, Iterable


KNOWLEDGE_SCHEMA = "agentos.knowledge/v1"
SYNTHESIS_SCHEMA = "agentos.synthesis/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}_{sha256(_canonical(payload).encode('utf-8')).hexdigest()[:32]}"


@dataclass(frozen=True)
class EvidenceRef:
    source_kind: str
    source_ref: str
    content_hash: str
    relation: str = "supports"  # supports|contradicts|context
    trust_class: str = "unverified"

    def __post_init__(self) -> None:
        if self.relation not in {"supports", "contradicts", "context"}:
            raise ValueError("invalid evidence relation")
        if not self.source_kind or not self.source_ref or not self.content_hash:
            raise ValueError("evidence source_kind, source_ref and content_hash are required")


@dataclass(frozen=True)
class KnowledgeCandidate:
    project_id: str
    kind: str
    statement: str
    abstraction_level: str = "project"  # working|project|cross_project
    confidence: float = 0.5
    status: str = "candidate"  # candidate|validated|superseded|rejected
    evidence: tuple[EvidenceRef, ...] = field(default_factory=tuple)
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    supersedes: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = KNOWLEDGE_SCHEMA

    def __post_init__(self) -> None:
        if not self.project_id or not self.kind or not self.statement:
            raise ValueError("project_id, kind and statement are required")
        if self.abstraction_level not in {"working", "project", "cross_project"}:
            raise ValueError("invalid abstraction_level")
        if self.status not in {"candidate", "validated", "superseded", "rejected"}:
            raise ValueError("invalid knowledge status")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def knowledge_id(self) -> str:
        payload = self.to_dict(include_id=False)
        return _id("know", payload)

    @property
    def contradiction_count(self) -> int:
        return sum(1 for item in self.evidence if item.relation == "contradicts")

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_id:
            value["knowledge_id"] = _id("know", value)
        return value


@dataclass(frozen=True)
class SynthesisRecord:
    project_id: str
    input_refs: tuple[str, ...]
    candidates: tuple[KnowledgeCandidate, ...]
    trigger_ref: str | None = None
    synthesis_kind: str = "incremental"  # incremental|global|cross_project|brainstorm
    schema_version: str = SYNTHESIS_SCHEMA

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("project_id is required")
        if self.synthesis_kind not in {"incremental", "global", "cross_project", "brainstorm"}:
            raise ValueError("invalid synthesis_kind")
        if not self.input_refs and not self.trigger_ref:
            raise ValueError("synthesis requires input_refs or trigger_ref")

    @property
    def synthesis_id(self) -> str:
        return _id("syn", self.to_dict(include_id=False))

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        value = {
            "project_id": self.project_id,
            "input_refs": list(self.input_refs),
            "candidates": [item.to_dict() for item in self.candidates],
            "trigger_ref": self.trigger_ref,
            "synthesis_kind": self.synthesis_kind,
            "schema_version": self.schema_version,
        }
        if include_id:
            value["synthesis_id"] = _id("syn", value)
        return value


def evidence_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def contradiction_refs(candidate: KnowledgeCandidate) -> tuple[EvidenceRef, ...]:
    return tuple(item for item in candidate.evidence if item.relation == "contradicts")


def merge_evidence(*groups: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Deterministically de-duplicate evidence without deleting contradictions."""
    values: dict[tuple[str, str, str, str], EvidenceRef] = {}
    for group in groups:
        for item in group:
            key = (item.source_kind, item.source_ref, item.content_hash, item.relation)
            values[key] = item
    return tuple(values[key] for key in sorted(values))

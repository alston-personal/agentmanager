"""Indexing and association contract for the AgentOS Cognitive Kernel.

This module intentionally does not implement a general vector database. It owns
AgentOS-specific retrieval semantics: direct relevance, structural analogy,
provenance preservation, and governed construction of a synthesis input set.
Storage/search backends remain replaceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Protocol, Sequence

from runtime_core.cognitive_ir import KnowledgeCandidate


_TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


def _norm_terms(values: Iterable[str]) -> frozenset[str]:
    terms: set[str] = set()
    for value in values:
        for token in _TOKEN_RE.findall(str(value).lower()):
            if len(token) >= 2:
                terms.add(token)
    return frozenset(terms)


@dataclass(frozen=True)
class CognitiveIndexRecord:
    """Backend-neutral projection of one knowledge candidate for retrieval."""

    knowledge_id: str
    project_id: str
    kind: str
    statement: str
    abstraction_level: str
    status: str
    confidence: float
    terms: frozenset[str] = field(default_factory=frozenset)
    concepts: frozenset[str] = field(default_factory=frozenset)
    structural_signatures: frozenset[str] = field(default_factory=frozenset)
    domain: str | None = None

    @classmethod
    def from_candidate(cls, candidate: KnowledgeCandidate) -> "CognitiveIndexRecord":
        metadata = candidate.metadata
        concepts = frozenset(
            str(item).strip().lower()
            for item in metadata.get("concepts", ())
            if str(item).strip()
        )
        signatures = frozenset(
            str(item).strip().lower()
            for item in metadata.get("structural_signatures", ())
            if str(item).strip()
        )
        terms = _norm_terms(
            [candidate.kind, candidate.statement, *concepts, *signatures]
        )
        domain = str(metadata.get("domain") or "").strip().lower() or None
        return cls(
            knowledge_id=candidate.knowledge_id,
            project_id=candidate.project_id,
            kind=candidate.kind,
            statement=candidate.statement,
            abstraction_level=candidate.abstraction_level,
            status=candidate.status,
            confidence=float(candidate.confidence),
            terms=terms,
            concepts=concepts,
            structural_signatures=signatures,
            domain=domain,
        )


@dataclass(frozen=True)
class AssociationQuery:
    text: str
    concepts: frozenset[str] = field(default_factory=frozenset)
    structural_signatures: frozenset[str] = field(default_factory=frozenset)
    project_id: str | None = None
    domain: str | None = None
    include_cross_project: bool = True
    include_superseded: bool = False
    include_archive: bool = False
    limit_near: int = 8
    limit_far: int = 4

    @property
    def terms(self) -> frozenset[str]:
        return _norm_terms([self.text, *self.concepts])


@dataclass(frozen=True)
class AssociationHit:
    knowledge_id: str
    mode: str  # near|far
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AssociationSet:
    """Disposable retrieval result; never canonical truth or durable memory."""

    trigger_ref: str
    query: AssociationQuery
    near: tuple[AssociationHit, ...]
    far: tuple[AssociationHit, ...]
    source_ids: tuple[str, ...]

    def synthesis_input_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self.source_ids]))


class CognitiveIndexBackend(Protocol):
    """Minimal backend contract; implementations may use FTS/vector/graph stores."""

    def upsert(self, records: Sequence[CognitiveIndexRecord]) -> None: ...

    def records(self) -> Sequence[CognitiveIndexRecord]: ...


class LifecycleStateLike(Protocol):
    tier: object

    @property
    def retrieval_weight(self) -> float: ...


class LifecycleStoreLike(Protocol):
    def get(self, knowledge_id: str) -> LifecycleStateLike | None: ...


class InMemoryCognitiveIndex:
    """Deterministic reference backend for tests/small deployments.

    This is intentionally simple and replaceable. It exists to validate AgentOS
    association semantics without making AgentOS own a search infrastructure.
    """

    def __init__(self) -> None:
        self._records: dict[str, CognitiveIndexRecord] = {}

    def upsert(self, records: Sequence[CognitiveIndexRecord]) -> None:
        for record in records:
            self._records[record.knowledge_id] = record

    def records(self) -> Sequence[CognitiveIndexRecord]:
        return tuple(self._records[key] for key in sorted(self._records))


class CognitiveAssociationEngine:
    """Build near and far retrieval sets while retaining exact source IDs."""

    def __init__(
        self,
        backend: CognitiveIndexBackend,
        *,
        lifecycle_store: LifecycleStoreLike | None = None,
    ) -> None:
        self.backend = backend
        self.lifecycle_store = lifecycle_store

    @staticmethod
    def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _lifecycle_weight(self, knowledge_id: str, query: AssociationQuery) -> float:
        if self.lifecycle_store is None:
            return 1.0
        state = self.lifecycle_store.get(knowledge_id)
        if state is None:
            return 1.0
        tier_name = getattr(state.tier, "name", str(state.tier)).upper()
        if tier_name == "ARCHIVE" and not query.include_archive:
            return 0.0
        return max(0.0, min(1.0, float(state.retrieval_weight)))

    def _eligible(self, record: CognitiveIndexRecord, query: AssociationQuery) -> bool:
        if not query.include_superseded and record.status in {"superseded", "rejected"}:
            return False
        if not query.include_cross_project and query.project_id and record.project_id != query.project_id:
            return False
        if self._lifecycle_weight(record.knowledge_id, query) <= 0:
            return False
        return True

    def retrieve(self, query: AssociationQuery, *, trigger_ref: str) -> AssociationSet:
        if not str(trigger_ref or "").strip():
            raise ValueError("trigger_ref is required for provenance")

        near_hits: list[AssociationHit] = []
        far_hits: list[AssociationHit] = []
        q_terms = query.terms
        q_concepts = frozenset(item.lower() for item in query.concepts)
        q_structures = frozenset(item.lower() for item in query.structural_signatures)
        q_domain = str(query.domain or "").lower() or None

        for record in self.backend.records():
            if not self._eligible(record, query):
                continue

            lifecycle_weight = self._lifecycle_weight(record.knowledge_id, query)
            term_score = self._jaccard(q_terms, record.terms)
            concept_score = self._jaccard(q_concepts, record.concepts)
            near_score = (0.65 * term_score + 0.35 * concept_score) * lifecycle_weight
            if near_score > 0:
                reasons = []
                if q_terms & record.terms:
                    reasons.append("shared_terms")
                if q_concepts & record.concepts:
                    reasons.append("shared_concepts")
                if query.project_id and record.project_id == query.project_id:
                    reasons.append("same_project")
                    near_score += 0.05 * lifecycle_weight
                if lifecycle_weight < 0.999:
                    reasons.append("lifecycle_weighted")
                near_hits.append(
                    AssociationHit(
                        knowledge_id=record.knowledge_id,
                        mode="near",
                        score=round(min(near_score, 1.0), 6),
                        reasons=tuple(reasons),
                    )
                )

            structure_score = self._jaccard(q_structures, record.structural_signatures)
            different_domain = bool(q_domain and record.domain and record.domain != q_domain)
            if structure_score > 0 and different_domain:
                lexical_penalty = min(term_score, 0.5) * 0.15
                far_score = max(0.0, structure_score - lexical_penalty) * lifecycle_weight
                reasons = ["shared_structure", "cross_domain"]
                if lifecycle_weight < 0.999:
                    reasons.append("lifecycle_weighted")
                far_hits.append(
                    AssociationHit(
                        knowledge_id=record.knowledge_id,
                        mode="far",
                        score=round(far_score, 6),
                        reasons=tuple(reasons),
                    )
                )

        near_hits.sort(key=lambda item: (-item.score, item.knowledge_id))
        far_hits.sort(key=lambda item: (-item.score, item.knowledge_id))
        near = tuple(near_hits[: max(0, query.limit_near)])
        far = tuple(far_hits[: max(0, query.limit_far)])
        source_ids = tuple(
            dict.fromkeys([*(item.knowledge_id for item in near), *(item.knowledge_id for item in far)])
        )
        return AssociationSet(
            trigger_ref=trigger_ref,
            query=query,
            near=near,
            far=far,
            source_ids=source_ids,
        )


def index_candidates(
    backend: CognitiveIndexBackend,
    candidates: Iterable[KnowledgeCandidate],
) -> tuple[CognitiveIndexRecord, ...]:
    records = tuple(CognitiveIndexRecord.from_candidate(item) for item in candidates)
    backend.upsert(records)
    return records

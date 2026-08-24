"""Relational memory and project knowledge graph for AgentOS.

The graph is deliberately not canonical ProjectState. It is a cognitive index
of stable entities and provenance-bearing relation claims used for discovery,
association and global re-synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Iterable

from runtime_core.relational_ir import EntityRecord, RelationRecord, normalize_alias


@dataclass(frozen=True)
class EntityMatch:
    entity_id: str
    score: float
    reason: str


@dataclass(frozen=True)
class RelationHop:
    depth: int
    relation_id: str
    subject_id: str
    predicate: str
    object_id: str


class InMemoryRelationGraph:
    """Deterministic reference graph; production graph/search backend is pluggable."""

    def __init__(self) -> None:
        self._entities: dict[str, EntityRecord] = {}
        self._relations: dict[str, RelationRecord] = {}

    def upsert_entities(self, entities: Iterable[EntityRecord]) -> None:
        for entity in entities:
            self._entities[entity.entity_id] = entity

    def add_relations(self, relations: Iterable[RelationRecord]) -> None:
        for relation in relations:
            if relation.subject_id not in self._entities or relation.object_id not in self._entities:
                raise ValueError("relation endpoints must be registered entities")
            self._relations[relation.relation_id] = relation

    def entity(self, entity_id: str) -> EntityRecord | None:
        return self._entities.get(entity_id)

    def entities(self) -> tuple[EntityRecord, ...]:
        return tuple(self._entities[key] for key in sorted(self._entities))

    def relations(self, *, include_inactive: bool = False) -> tuple[RelationRecord, ...]:
        values = self._relations.values()
        if not include_inactive:
            values = (item for item in values if item.status not in {"superseded", "rejected"})
        return tuple(sorted(values, key=lambda item: item.relation_id))

    def resolve(self, query: str, *, limit: int = 8) -> tuple[EntityMatch, ...]:
        """Resolve conversational names/aliases/refs to known graph identities."""
        needle = normalize_alias(query)
        if not needle:
            return ()
        needle_terms = frozenset(needle.split())
        hits: list[EntityMatch] = []
        for entity in self._entities.values():
            best_score = 0.0
            best_reason = ""
            for name in entity.search_names:
                if needle == name:
                    score, reason = 1.0, "exact_alias"
                elif needle in name or name in needle:
                    score, reason = 0.82, "substring_alias"
                else:
                    terms = frozenset(name.split())
                    if not needle_terms or not terms:
                        continue
                    overlap = len(needle_terms & terms) / len(needle_terms | terms)
                    score, reason = overlap * 0.70, "shared_alias_terms"
                if score > best_score:
                    best_score, best_reason = score, reason
            if best_score > 0:
                hits.append(EntityMatch(entity.entity_id, round(best_score, 6), best_reason))
        hits.sort(key=lambda item: (-item.score, item.entity_id))
        return tuple(hits[: max(0, limit)])

    def neighbors(
        self,
        entity_id: str,
        *,
        predicates: frozenset[str] | None = None,
        direction: str = "both",
        include_inactive: bool = False,
    ) -> tuple[RelationRecord, ...]:
        if direction not in {"out", "in", "both"}:
            raise ValueError("direction must be out, in or both")
        results: list[RelationRecord] = []
        for relation in self.relations(include_inactive=include_inactive):
            if predicates and relation.predicate not in predicates:
                continue
            outgoing = direction in {"out", "both"} and relation.subject_id == entity_id
            incoming = direction in {"in", "both"} and relation.object_id == entity_id
            if outgoing or incoming:
                results.append(relation)
        return tuple(results)

    def walk(
        self,
        start_id: str,
        *,
        max_depth: int = 2,
        predicates: frozenset[str] | None = None,
        include_inactive: bool = False,
    ) -> tuple[RelationHop, ...]:
        """Bounded graph traversal for discovery; cycles are suppressed."""
        if start_id not in self._entities:
            raise KeyError(start_id)
        if max_depth < 0:
            raise ValueError("max_depth cannot be negative")
        queue = deque([(start_id, 0)])
        expanded = {start_id}
        seen_relations: set[str] = set()
        hops: list[RelationHop] = []
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for relation in self.neighbors(
                current,
                predicates=predicates,
                direction="both",
                include_inactive=include_inactive,
            ):
                if relation.relation_id not in seen_relations:
                    hops.append(
                        RelationHop(
                            depth=depth + 1,
                            relation_id=relation.relation_id,
                            subject_id=relation.subject_id,
                            predicate=relation.predicate,
                            object_id=relation.object_id,
                        )
                    )
                    seen_relations.add(relation.relation_id)
                other = relation.object_id if relation.subject_id == current else relation.subject_id
                if other not in expanded:
                    expanded.add(other)
                    queue.append((other, depth + 1))
        hops.sort(key=lambda item: (item.depth, item.relation_id))
        return tuple(hops)

    def related_entity_ids(
        self,
        query: str,
        *,
        max_depth: int = 2,
        predicates: frozenset[str] | None = None,
    ) -> tuple[str, ...]:
        """Resolve an alias then return the bounded relation neighborhood."""
        matches = self.resolve(query, limit=1)
        if not matches:
            return ()
        start_id = matches[0].entity_id
        ids = [start_id]
        for hop in self.walk(start_id, max_depth=max_depth, predicates=predicates):
            ids.extend((hop.subject_id, hop.object_id))
        return tuple(dict.fromkeys(ids))

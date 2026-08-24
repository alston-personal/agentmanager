"""Load bounded shadow relation seeds into the Cognitive Kernel graph.

Seed files are discovery/bootstrap inputs, not canonical truth. Their relation
status and evidence are preserved exactly so candidate edges remain candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_core.relational_memory import InMemoryRelationGraph
from runtime_core.relational_ir import EntityRecord, RelationEvidence, RelationRecord


RELATION_SEED_SCHEMA = "agentos.relation-seed/v1"


@dataclass(frozen=True)
class LoadedRelationSeed:
    mode: str
    entities: tuple[EntityRecord, ...]
    relations: tuple[RelationRecord, ...]

    def build_graph(self) -> InMemoryRelationGraph:
        graph = InMemoryRelationGraph()
        graph.upsert_entities(self.entities)
        graph.add_relations(self.relations)
        return graph


def _tuple_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("expected list of strings")
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise ValueError("blank string is not allowed")
    return result


def load_relation_seed(payload: Mapping[str, Any]) -> LoadedRelationSeed:
    if payload.get("schema_version") != RELATION_SEED_SCHEMA:
        raise ValueError("unsupported relation seed schema")
    mode = str(payload.get("mode") or "").strip()
    if mode != "shadow":
        raise ValueError("relation seeds must load in shadow mode")

    raw_entities = payload.get("entities")
    raw_relations = payload.get("relations")
    if not isinstance(raw_entities, list) or not isinstance(raw_relations, list):
        raise ValueError("entities and relations must be lists")

    entities: list[EntityRecord] = []
    seen_entity_ids: set[str] = set()
    for raw in raw_entities:
        if not isinstance(raw, Mapping):
            raise ValueError("entity must be an object")
        entity = EntityRecord(
            entity_id=str(raw.get("entity_id") or ""),
            kind=str(raw.get("kind") or ""),
            canonical_name=str(raw.get("canonical_name") or ""),
            aliases=_tuple_strings(raw.get("aliases")),
            refs=_tuple_strings(raw.get("refs")),
            metadata=dict(raw.get("metadata") or {}),
        )
        if entity.entity_id in seen_entity_ids:
            raise ValueError(f"duplicate entity_id: {entity.entity_id}")
        seen_entity_ids.add(entity.entity_id)
        entities.append(entity)

    relations: list[RelationRecord] = []
    for raw in raw_relations:
        if not isinstance(raw, Mapping):
            raise ValueError("relation must be an object")
        raw_evidence = raw.get("evidence") or []
        if not isinstance(raw_evidence, list):
            raise ValueError("relation evidence must be a list")
        evidence = tuple(
            RelationEvidence(
                source_kind=str(item.get("source_kind") or ""),
                source_ref=str(item.get("source_ref") or ""),
                content_hash=str(item.get("content_hash") or ""),
                trust_class=str(item.get("trust_class") or "observed"),
            )
            for item in raw_evidence
            if isinstance(item, Mapping)
        )
        if len(evidence) != len(raw_evidence):
            raise ValueError("relation evidence entries must be objects")
        relation = RelationRecord(
            subject_id=str(raw.get("subject_id") or ""),
            predicate=str(raw.get("predicate") or ""),
            object_id=str(raw.get("object_id") or ""),
            evidence=evidence,
            confidence=float(raw.get("confidence", 0.5)),
            status=str(raw.get("status") or "candidate"),
            valid_from=raw.get("valid_from"),
            valid_to=raw.get("valid_to"),
            metadata=dict(raw.get("metadata") or {}),
        )
        if relation.status == "validated" and not relation.evidence:
            raise ValueError("validated relation requires evidence")
        if any("pending" in item.content_hash.lower() for item in relation.evidence):
            raise ValueError("placeholder evidence hashes are forbidden")
        relations.append(relation)

    loaded = LoadedRelationSeed(mode=mode, entities=tuple(entities), relations=tuple(relations))
    # Endpoint validation happens here too, so a seed cannot smuggle dangling edges.
    loaded.build_graph()
    return loaded

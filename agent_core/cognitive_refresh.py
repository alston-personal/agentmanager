"""Dependency-driven re-synthesis planning for the Cognitive Kernel.

A new input may invalidate, challenge, or enrich earlier synthesis. This module
plans re-synthesis work; it never promotes knowledge or executes external side
effects. Re-synthesis is therefore an epistemic proposal workflow, not an
autonomous truth mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from agent_core.cognitive_index import AssociationSet
from runtime_core.cognitive_ir import KnowledgeCandidate, SynthesisRecord


@dataclass(frozen=True)
class ResynthesisRequest:
    synthesis_id: str
    trigger_ref: str
    affected_source_ids: tuple[str, ...]
    newly_associated_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    priority: int


class SynthesisDependencyIndex:
    """Small deterministic dependency graph from knowledge -> syntheses."""

    def __init__(self) -> None:
        self._records: dict[str, SynthesisRecord] = {}
        self._by_source: dict[str, set[str]] = {}

    def register(self, record: SynthesisRecord) -> None:
        synthesis_id = record.synthesis_id
        self._records[synthesis_id] = record
        for source_id in record.input_refs:
            self._by_source.setdefault(source_id, set()).add(synthesis_id)
        for candidate in record.candidates:
            for source_id in candidate.derived_from:
                self._by_source.setdefault(source_id, set()).add(synthesis_id)

    def get(self, synthesis_id: str) -> SynthesisRecord | None:
        return self._records.get(synthesis_id)

    def dependent_syntheses(self, knowledge_ids: Iterable[str]) -> tuple[str, ...]:
        values: set[str] = set()
        for knowledge_id in knowledge_ids:
            values.update(self._by_source.get(knowledge_id, ()))
        return tuple(sorted(values))


class CognitiveRefreshPlanner:
    """Plans which prior syntheses should be reconsidered after a new input."""

    def __init__(self, dependencies: SynthesisDependencyIndex) -> None:
        self.dependencies = dependencies

    def plan(
        self,
        trigger: KnowledgeCandidate,
        associations: AssociationSet,
    ) -> tuple[ResynthesisRequest, ...]:
        trigger_ref = trigger.knowledge_id
        changed_ids = set(trigger.supersedes)
        contradiction_targets = set(
            str(item).strip()
            for item in trigger.metadata.get("contradicts_knowledge_ids", ())
            if str(item).strip()
        )
        changed_ids.update(contradiction_targets)

        associated_ids = set(associations.source_ids)
        directly_affected = set(self.dependencies.dependent_syntheses(changed_ids))
        enriched = set(self.dependencies.dependent_syntheses(associated_ids))
        synthesis_ids = directly_affected | enriched

        requests: list[ResynthesisRequest] = []
        for synthesis_id in sorted(synthesis_ids):
            record = self.dependencies.get(synthesis_id)
            if record is None:
                continue
            existing_sources = set(record.input_refs)
            affected = tuple(sorted(existing_sources & changed_ids))
            newly_associated = tuple(sorted(associated_ids - existing_sources))
            reasons: list[str] = []
            priority = 10

            if set(affected) & set(trigger.supersedes):
                reasons.append("source_superseded")
                priority += 40
            if set(affected) & contradiction_targets:
                reasons.append("new_contradiction")
                priority += 50
            if newly_associated:
                reasons.append("new_association")
                priority += 10
            if any(hit.mode == "far" and hit.knowledge_id in newly_associated for hit in associations.far):
                reasons.append("new_structural_analogy")
                priority += 10

            # Purely incidental association with no changed/new source should not
            # churn the synthesis graph.
            if not reasons:
                continue
            requests.append(
                ResynthesisRequest(
                    synthesis_id=synthesis_id,
                    trigger_ref=trigger_ref,
                    affected_source_ids=affected,
                    newly_associated_ids=newly_associated,
                    reasons=tuple(sorted(set(reasons))),
                    priority=priority,
                )
            )

        requests.sort(key=lambda item: (-item.priority, item.synthesis_id))
        return tuple(requests)

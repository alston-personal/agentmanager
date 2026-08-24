"""Hierarchical compaction and meta-synthesis planning for Cognitive Kernel.

Already-synthesized knowledge may become input to later synthesis. The key
invariant is that compaction never severs provenance: a meta-level candidate
must still be traceable through knowledge lineage to original ExperienceEvent
IDs or other externally anchored source refs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from runtime_core.cognitive_ir import KnowledgeCandidate


@dataclass(frozen=True)
class MetaSynthesisPlan:
    project_id: str
    synthesis_kind: str
    source_knowledge_ids: tuple[str, ...]
    root_experience_ids: tuple[str, ...]
    root_external_refs: tuple[str, ...]
    reason: str


class KnowledgeLineageResolver:
    """Resolve candidate lineage back to durable source anchors."""

    def __init__(self, lookup: Callable[[str], KnowledgeCandidate | None]) -> None:
        self.lookup = lookup

    def roots(self, knowledge_ids: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        experience: set[str] = set()
        external: set[str] = set()
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(ref: str) -> None:
            if ref in visited:
                return
            if ref in visiting:
                raise ValueError(f"knowledge lineage cycle detected at {ref}")
            if ref.startswith("exp_"):
                experience.add(ref)
                visited.add(ref)
                return
            candidate = self.lookup(ref)
            if candidate is None:
                external.add(ref)
                visited.add(ref)
                return
            visiting.add(ref)
            if candidate.derived_from:
                for parent in candidate.derived_from:
                    visit(parent)
            else:
                # Evidence source refs are durable external anchors when a
                # candidate does not carry explicit knowledge/event lineage.
                for item in candidate.evidence:
                    external.add(f"{item.source_kind}:{item.source_ref}:{item.content_hash}")
            visiting.remove(ref)
            visited.add(ref)

        for knowledge_id in knowledge_ids:
            visit(knowledge_id)
        return tuple(sorted(experience)), tuple(sorted(external))


class CognitiveCompactionPlanner:
    """Plan higher-order synthesis without repeatedly rereading raw history."""

    def __init__(
        self,
        lookup: Callable[[str], KnowledgeCandidate | None],
        *,
        max_sources: int = 12,
    ) -> None:
        if max_sources < 2:
            raise ValueError("max_sources must be at least 2")
        self.lookup = lookup
        self.max_sources = max_sources
        self.lineage = KnowledgeLineageResolver(lookup)

    def plan_project_compaction(
        self,
        candidates: Sequence[KnowledgeCandidate],
        *,
        project_id: str,
    ) -> tuple[MetaSynthesisPlan, ...]:
        eligible = [
            item
            for item in candidates
            if item.project_id == project_id
            and item.status == "validated"
            and item.abstraction_level in {"project", "cross_project"}
        ]
        # Stable deterministic ordering: more confident reusable knowledge first,
        # then content-addressed ID for reproducibility.
        eligible.sort(key=lambda item: (-item.confidence, item.knowledge_id))
        plans: list[MetaSynthesisPlan] = []
        for index in range(0, len(eligible), self.max_sources):
            group = eligible[index : index + self.max_sources]
            if len(group) < 2:
                continue
            ids = tuple(item.knowledge_id for item in group)
            experience, external = self.lineage.roots(ids)
            plans.append(
                MetaSynthesisPlan(
                    project_id=project_id,
                    synthesis_kind="global",
                    source_knowledge_ids=ids,
                    root_experience_ids=experience,
                    root_external_refs=external,
                    reason="compact validated project knowledge into a higher-order synthesis",
                )
            )
        return tuple(plans)

    def plan_cross_project(
        self,
        candidates: Sequence[KnowledgeCandidate],
    ) -> tuple[MetaSynthesisPlan, ...]:
        eligible = [
            item
            for item in candidates
            if item.status == "validated" and item.abstraction_level == "cross_project"
        ]
        by_concept: dict[str, list[KnowledgeCandidate]] = {}
        for item in eligible:
            concepts = {
                str(value).strip().lower()
                for value in item.metadata.get("concepts", ())
                if str(value).strip()
            }
            for concept in concepts:
                by_concept.setdefault(concept, []).append(item)

        plans: list[MetaSynthesisPlan] = []
        seen_groups: set[tuple[str, ...]] = set()
        for concept in sorted(by_concept):
            values = by_concept[concept]
            projects = {item.project_id for item in values}
            if len(projects) < 2:
                continue
            values.sort(key=lambda item: (-item.confidence, item.knowledge_id))
            ids = tuple(item.knowledge_id for item in values[: self.max_sources])
            if len(ids) < 2 or ids in seen_groups:
                continue
            seen_groups.add(ids)
            experience, external = self.lineage.roots(ids)
            plans.append(
                MetaSynthesisPlan(
                    project_id="__cross_project__",
                    synthesis_kind="cross_project",
                    source_knowledge_ids=ids,
                    root_experience_ids=experience,
                    root_external_refs=external,
                    reason=f"cross-project concept convergence: {concept}",
                )
            )
        return tuple(plans)

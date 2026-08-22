"""Read-only projection of AgentOS cognition into longitudinal observatory data."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from agent_core.cognitive_memory_lifecycle import MemoryLifecycleState, MemoryTier
from agent_core.cognitive_reconciliation import GlobalReconciliationPlan
from runtime_core.cognitive_ir import KnowledgeCandidate
from runtime_core.observatory_v1 import CognitiveDelta, CognitiveMetrics, CognitiveSnapshot
from runtime_core.relational_ir import EntityRecord, RelationRecord


class CognitiveObservatory:
    """Build descriptive snapshots/deltas without mutating any source subsystem."""

    @staticmethod
    def snapshot(
        *,
        project_id: str,
        captured_at: str,
        trigger_ref: str,
        knowledge: Iterable[KnowledgeCandidate] = (),
        entities: Iterable[EntityRecord] = (),
        relations: Iterable[RelationRecord] = (),
        lifecycle: Iterable[MemoryLifecycleState] = (),
        reconciliation: GlobalReconciliationPlan | None = None,
        annotations: Iterable[str] = (),
    ) -> CognitiveSnapshot:
        knowledge = tuple(knowledge)
        entities = tuple(entities)
        relations = tuple(relations)
        lifecycle = tuple(lifecycle)

        knowledge_ids = tuple(sorted(item.knowledge_id for item in knowledge))
        entity_ids = tuple(sorted(item.entity_id for item in entities))
        relation_ids = tuple(sorted(item.relation_id for item in relations))
        archived = tuple(
            sorted(item.knowledge_id for item in lifecycle if item.tier == MemoryTier.ARCHIVE)
        )
        issues = tuple(reconciliation.issues) if reconciliation else ()

        metrics = CognitiveMetrics(
            knowledge_count=len(knowledge),
            validated_knowledge_count=sum(item.status == "validated" for item in knowledge),
            superseded_knowledge_count=sum(item.status == "superseded" for item in knowledge),
            contradiction_count=sum(item.contradiction_count for item in knowledge),
            entity_count=len(entities),
            relation_count=len(relations),
            validated_relation_count=sum(item.status == "validated" for item in relations),
            orphan_entity_count=sum(item.kind == "orphan_entity" for item in issues),
            ungrounded_relation_count=sum(item.kind == "ungrounded_relation" for item in issues),
            stale_derivative_count=sum(item.kind == "stale_derivative" for item in issues),
            archive_memory_count=len(archived),
        )
        return CognitiveSnapshot(
            project_id=project_id,
            captured_at=captured_at,
            trigger_ref=trigger_ref,
            knowledge_ids=knowledge_ids,
            relation_ids=relation_ids,
            entity_ids=entity_ids,
            archived_knowledge_ids=archived,
            metrics=metrics,
            annotations=tuple(dict.fromkeys(str(item) for item in annotations if str(item))),
        )

    @staticmethod
    def diff(before: CognitiveSnapshot, after: CognitiveSnapshot, *, annotations: Iterable[str] = ()) -> CognitiveDelta:
        if before.project_id != after.project_id:
            raise ValueError("cannot diff cognitive snapshots from different projects")
        before_knowledge = set(before.knowledge_ids)
        after_knowledge = set(after.knowledge_ids)
        before_relations = set(before.relation_ids)
        after_relations = set(after.relation_ids)
        before_archive = set(before.archived_knowledge_ids)
        after_archive = set(after.archived_knowledge_ids)
        before_metrics = asdict(before.metrics)
        after_metrics = asdict(after.metrics)
        return CognitiveDelta(
            project_id=before.project_id,
            from_snapshot_id=before.snapshot_id,
            to_snapshot_id=after.snapshot_id,
            added_knowledge_ids=tuple(sorted(after_knowledge - before_knowledge)),
            removed_knowledge_ids=tuple(sorted(before_knowledge - after_knowledge)),
            added_relation_ids=tuple(sorted(after_relations - before_relations)),
            removed_relation_ids=tuple(sorted(before_relations - after_relations)),
            newly_archived_knowledge_ids=tuple(sorted(after_archive - before_archive)),
            revived_knowledge_ids=tuple(sorted(before_archive - after_archive)),
            metric_delta={
                name: after_metrics[name] - before_metrics[name]
                for name in sorted(before_metrics)
                if after_metrics[name] != before_metrics[name]
            },
            annotations=tuple(dict.fromkeys(str(item) for item in annotations if str(item))),
        )

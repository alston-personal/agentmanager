"""Global relational reconciliation planning for the Cognitive Kernel.

Reconciliation does not rewrite memory. It inspects the relation graph for
missing links, stale derived artifacts and weakly grounded cross-project claims,
then emits bounded reconsideration work that an external synthesizer or human
may review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from agent_core.relational_memory import InMemoryRelationGraph
from runtime_core.relational_ir import RelationRecord


@dataclass(frozen=True)
class ReconciliationIssue:
    kind: str
    subject_ref: str
    related_ref: str | None
    priority: int
    reason: str


@dataclass(frozen=True)
class GlobalReconciliationPlan:
    trigger_ref: str
    entity_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    issues: tuple[ReconciliationIssue, ...]

    @property
    def requires_work(self) -> bool:
        return bool(self.issues)


class CognitiveReconciliationPlanner:
    """Reference planner for global re-association / meta-synthesis maintenance."""

    def __init__(self, graph: InMemoryRelationGraph) -> None:
        self.graph = graph

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        if value in {None, ""}:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _is_cross_project(relation: RelationRecord, graph: InMemoryRelationGraph) -> bool:
        subject = graph.entity(relation.subject_id)
        obj = graph.entity(relation.object_id)
        if not subject or not obj:
            return False
        subject_project = str(subject.metadata.get("project_id") or "")
        object_project = str(obj.metadata.get("project_id") or "")
        return bool(subject_project and object_project and subject_project != object_project)

    def plan(
        self,
        *,
        trigger_ref: str,
        focus_entity_ids: Iterable[str] | None = None,
    ) -> GlobalReconciliationPlan:
        if not str(trigger_ref or "").strip():
            raise ValueError("trigger_ref is required")
        if focus_entity_ids is None:
            entity_ids = tuple(item.entity_id for item in self.graph.entities())
        else:
            entity_ids = tuple(dict.fromkeys(str(item) for item in focus_entity_ids))
            unknown = [item for item in entity_ids if self.graph.entity(item) is None]
            if unknown:
                raise KeyError(unknown[0])

        focus = set(entity_ids)
        relations = tuple(
            item
            for item in self.graph.relations()
            if item.subject_id in focus or item.object_id in focus
        )
        issues: list[ReconciliationIssue] = []

        # Isolated cognitive entities are discoverable but cannot contribute to
        # cross-project reasoning until at least one explicit relationship exists.
        connected: set[str] = set()
        for relation in relations:
            connected.add(relation.subject_id)
            connected.add(relation.object_id)
        for entity_id in entity_ids:
            if entity_id not in connected:
                issues.append(
                    ReconciliationIssue(
                        kind="orphan_entity",
                        subject_ref=entity_id,
                        related_ref=None,
                        priority=40,
                        reason="entity has no explicit relation edge",
                    )
                )

        for relation in relations:
            if not relation.evidence:
                issues.append(
                    ReconciliationIssue(
                        kind="ungrounded_relation",
                        subject_ref=relation.subject_id,
                        related_ref=relation.object_id,
                        priority=90,
                        reason=f"{relation.predicate} has no provenance evidence",
                    )
                )

            if self._is_cross_project(relation, self.graph) and relation.status != "validated":
                issues.append(
                    ReconciliationIssue(
                        kind="cross_project_relation_review",
                        subject_ref=relation.subject_id,
                        related_ref=relation.object_id,
                        priority=80,
                        reason="cross-project relation is not validated",
                    )
                )

            # Derived artifacts can declare their last source snapshot and own
            # update time in metadata. A newer source means the derivative should
            # be reconsidered, not silently rewritten.
            if relation.predicate in {
                "derived_from",
                "fictionalized_from",
                "summarized_from",
                "compiled_from",
            }:
                derived = self.graph.entity(relation.subject_id)
                source = self.graph.entity(relation.object_id)
                if derived and source:
                    derived_at = self._parse_time(derived.metadata.get("updated_at"))
                    source_at = self._parse_time(source.metadata.get("updated_at"))
                    if derived_at and source_at and source_at > derived_at:
                        issues.append(
                            ReconciliationIssue(
                                kind="stale_derivative",
                                subject_ref=derived.entity_id,
                                related_ref=source.entity_id,
                                priority=85,
                                reason="source evolved after derived artifact was last updated",
                            )
                        )

        issues.sort(key=lambda item: (-item.priority, item.kind, item.subject_ref, item.related_ref or ""))
        return GlobalReconciliationPlan(
            trigger_ref=trigger_ref,
            entity_ids=entity_ids,
            relation_ids=tuple(item.relation_id for item in relations),
            issues=tuple(issues),
        )

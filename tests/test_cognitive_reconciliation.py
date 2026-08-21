from agent_core.cognitive_reconciliation import CognitiveReconciliationPlanner
from agent_core.relational_memory import InMemoryRelationGraph
from runtime_core.relational_ir import EntityRecord, RelationEvidence, RelationRecord


def ev(ref: str) -> tuple[RelationEvidence, ...]:
    return (RelationEvidence("github", ref, "b" * 64, trust_class="observed"),)


def graph_for_reconciliation() -> InMemoryRelationGraph:
    graph = InMemoryRelationGraph()
    graph.upsert_entities(
        (
            EntityRecord(
                "artifact:grand-chronicle",
                "artifact",
                "AgentOS Grand Chronicle",
                aliases=("AgentOS 編年史",),
                metadata={"project_id": "agentmanager", "updated_at": "2026-08-21T12:00:00Z"},
            ),
            EntityRecord(
                "work:ai-fantasy",
                "creative_work",
                "AI 奇幻編年史",
                aliases=("同源雙模小說",),
                metadata={"project_id": "zeus-writer", "updated_at": "2026-04-20T00:00:00Z"},
            ),
            EntityRecord(
                "project:orphan",
                "project",
                "Forgotten Project",
                metadata={"project_id": "orphan"},
            ),
        )
    )
    graph.add_relations(
        (
            RelationRecord(
                "work:ai-fantasy",
                "fictionalized_from",
                "artifact:grand-chronicle",
                evidence=ev("zeus-writer:寫作計畫.md"),
                confidence=0.9,
                status="validated",
            ),
        )
    )
    return graph


def test_reconciliation_detects_stale_derivative_and_orphan():
    plan = CognitiveReconciliationPlanner(graph_for_reconciliation()).plan(
        trigger_ref="manual:global-reassociation"
    )
    kinds = {item.kind for item in plan.issues}
    assert "stale_derivative" in kinds
    assert "orphan_entity" in kinds
    stale = next(item for item in plan.issues if item.kind == "stale_derivative")
    assert stale.subject_ref == "work:ai-fantasy"
    assert stale.related_ref == "artifact:grand-chronicle"
    assert plan.requires_work is True


def test_ungrounded_relation_is_high_priority_review():
    graph = InMemoryRelationGraph()
    graph.upsert_entities(
        (
            EntityRecord("a", "project", "A", metadata={"project_id": "a"}),
            EntityRecord("b", "project", "B", metadata={"project_id": "b"}),
        )
    )
    graph.add_relations((RelationRecord("a", "related_to", "b", confidence=0.5),))
    plan = CognitiveReconciliationPlanner(graph).plan(trigger_ref="test")
    assert plan.issues[0].kind == "ungrounded_relation"
    assert any(item.kind == "cross_project_relation_review" for item in plan.issues)


def test_validated_current_derivative_needs_no_staleness_work():
    graph = graph_for_reconciliation()
    source = graph.entity("artifact:grand-chronicle")
    derived = graph.entity("work:ai-fantasy")
    orphan = graph.entity("project:orphan")
    graph.upsert_entities(
        (
            EntityRecord(
                derived.entity_id,
                derived.kind,
                derived.canonical_name,
                aliases=derived.aliases,
                metadata={"project_id": "zeus-writer", "updated_at": "2026-08-22T00:00:00Z"},
            ),
            source,
            orphan,
        )
    )
    plan = CognitiveReconciliationPlanner(graph).plan(
        trigger_ref="test",
        focus_entity_ids=("work:ai-fantasy", "artifact:grand-chronicle"),
    )
    assert all(item.kind != "stale_derivative" for item in plan.issues)


def test_unknown_focus_fails_closed():
    planner = CognitiveReconciliationPlanner(graph_for_reconciliation())
    try:
        planner.plan(trigger_ref="test", focus_entity_ids=("missing",))
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown focus entity must fail closed")

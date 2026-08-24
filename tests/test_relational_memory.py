from runtime_core.relational_ir import EntityRecord, RelationEvidence, RelationRecord
from agent_core.relational_memory import InMemoryRelationGraph


def evidence(ref: str) -> tuple[RelationEvidence, ...]:
    return (
        RelationEvidence(
            source_kind="github",
            source_ref=ref,
            content_hash="a" * 64,
            trust_class="observed",
        ),
    )


def build_graph() -> InMemoryRelationGraph:
    graph = InMemoryRelationGraph()
    graph.upsert_entities(
        (
            EntityRecord(
                entity_id="project:agentmanager",
                kind="project",
                canonical_name="AgentManager",
                aliases=("AgentOS", "Distributed AgentOS"),
                refs=("alston-personal/agentmanager",),
            ),
            EntityRecord(
                entity_id="artifact:grand-chronicle",
                kind="artifact",
                canonical_name="AgentOS Grand Chronicle",
                aliases=("AgentOS 編年史", "GRAND_CHRONICLE"),
                refs=("alston-personal/my-agent-data/GRAND_CHRONICLE.md",),
            ),
            EntityRecord(
                entity_id="project:zeus-writer",
                kind="project",
                canonical_name="Zeus Writer",
                aliases=("Zeus-writer", "同源雙模小說", "小說專案"),
                refs=("alston-personal/zeus-writer",),
            ),
            EntityRecord(
                entity_id="work:ai-fantasy-chronicles",
                kind="creative_work",
                canonical_name="AI 奇幻編年史",
                aliases=("代碼與靈魂的交織",),
                refs=("zeus-writer/AI_奇幻編年史",),
            ),
            EntityRecord(
                entity_id="chapter:ai-fantasy-09",
                kind="chapter",
                canonical_name="第09章 靈魂解構",
                aliases=("Logic/Data 2.0 小說章節",),
            ),
        )
    )
    graph.add_relations(
        (
            RelationRecord(
                subject_id="project:agentmanager",
                predicate="documented_by",
                object_id="artifact:grand-chronicle",
                evidence=evidence("my-agent-data:GRAND_CHRONICLE.md"),
                confidence=0.95,
                status="validated",
            ),
            RelationRecord(
                subject_id="project:zeus-writer",
                predicate="contains",
                object_id="work:ai-fantasy-chronicles",
                evidence=evidence("zeus-writer:tree"),
                confidence=0.99,
                status="validated",
            ),
            RelationRecord(
                subject_id="work:ai-fantasy-chronicles",
                predicate="fictionalized_from",
                object_id="artifact:grand-chronicle",
                evidence=evidence("zeus-writer:寫作計畫.md"),
                confidence=0.98,
                status="validated",
            ),
            RelationRecord(
                subject_id="work:ai-fantasy-chronicles",
                predicate="contains",
                object_id="chapter:ai-fantasy-09",
                evidence=evidence("zeus-writer:寫作計畫.md"),
                confidence=0.99,
                status="validated",
            ),
        )
    )
    return graph


def test_alias_resolution_finds_project_without_repo_name():
    graph = build_graph()
    matches = graph.resolve("同源雙模小說")
    assert matches
    assert matches[0].entity_id == "project:zeus-writer"
    assert matches[0].reason == "exact_alias"


def test_relation_walk_connects_novel_to_source_chronicle():
    graph = build_graph()
    ids = graph.related_entity_ids("同源雙模小說", max_depth=2)
    assert "project:zeus-writer" in ids
    assert "work:ai-fantasy-chronicles" in ids
    assert "artifact:grand-chronicle" in ids


def test_inactive_relations_are_hidden_by_default_but_auditable():
    graph = build_graph()
    graph.add_relations(
        (
            RelationRecord(
                subject_id="work:ai-fantasy-chronicles",
                predicate="derived_from",
                object_id="project:agentmanager",
                evidence=evidence("legacy-link"),
                confidence=0.6,
                status="superseded",
            ),
        )
    )
    assert all(item.status != "superseded" for item in graph.relations())
    assert any(item.status == "superseded" for item in graph.relations(include_inactive=True))


def test_relation_endpoints_must_be_registered():
    graph = InMemoryRelationGraph()
    graph.upsert_entities((EntityRecord("project:a", "project", "A"),))
    relation = RelationRecord("project:a", "contains", "artifact:missing")
    try:
        graph.add_relations((relation,))
    except ValueError as exc:
        assert "endpoints" in str(exc)
    else:
        raise AssertionError("unknown relation endpoint must fail closed")


def test_graph_walk_is_bounded_and_cycle_safe():
    graph = build_graph()
    graph.add_relations(
        (
            RelationRecord(
                subject_id="artifact:grand-chronicle",
                predicate="inspires",
                object_id="project:zeus-writer",
                evidence=evidence("cycle"),
                confidence=0.8,
                status="validated",
            ),
        )
    )
    hops = graph.walk("project:zeus-writer", max_depth=4)
    assert len({item.relation_id for item in hops}) == len(hops)
    assert len(hops) <= len(graph.relations())

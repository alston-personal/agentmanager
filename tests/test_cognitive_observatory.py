from agent_core.cognitive_memory_lifecycle import MemoryLifecycleState, MemoryTier
from agent_core.cognitive_observatory import CognitiveObservatory
from agent_core.cognitive_reconciliation import GlobalReconciliationPlan, ReconciliationIssue
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash
from runtime_core.relational_ir import EntityRecord, RelationEvidence, RelationRecord


def knowledge(statement: str, *, status="validated", contradiction=False):
    evidence = [
        EvidenceRef("test", f"src:{statement}", evidence_hash(statement), trust_class="verified")
    ]
    if contradiction:
        evidence.append(
            EvidenceRef("review", f"contra:{statement}", evidence_hash("counter" + statement), relation="contradicts", trust_class="verified")
        )
    return KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement=statement,
        confidence=0.9,
        status=status,
        evidence=tuple(evidence),
    )


def test_observatory_snapshot_is_descriptive_and_content_addressed():
    k1 = knowledge("state belongs to project")
    k2 = knowledge("old rule", status="superseded", contradiction=True)
    e1 = EntityRecord("entity:a", "concept", "A")
    e2 = EntityRecord("entity:b", "concept", "B")
    rel = RelationRecord(
        "entity:a",
        "related_to",
        "entity:b",
        evidence=(RelationEvidence("test", "edge", evidence_hash("edge")),),
        confidence=0.9,
        status="validated",
    )
    lifecycle = (
        MemoryLifecycleState(k1.knowledge_id, tier=MemoryTier.HOT, activation=1.0),
        MemoryLifecycleState(k2.knowledge_id, tier=MemoryTier.ARCHIVE, activation=0.05),
    )
    reconciliation = GlobalReconciliationPlan(
        trigger_ref="review:1",
        entity_ids=(e1.entity_id, e2.entity_id),
        relation_ids=(rel.relation_id,),
        issues=(
            ReconciliationIssue("stale_derivative", e1.entity_id, e2.entity_id, 85, "stale"),
        ),
    )
    snap = CognitiveObservatory.snapshot(
        project_id="agentmanager",
        captured_at="2026-08-22T04:00:00Z",
        trigger_ref="review:1",
        knowledge=(k1, k2),
        entities=(e1, e2),
        relations=(rel,),
        lifecycle=lifecycle,
        reconciliation=reconciliation,
    )
    assert snap.metrics.knowledge_count == 2
    assert snap.metrics.validated_knowledge_count == 1
    assert snap.metrics.superseded_knowledge_count == 1
    assert snap.metrics.contradiction_count == 1
    assert snap.metrics.validated_relation_ratio == 1.0
    assert snap.metrics.stale_derivative_count == 1
    assert snap.metrics.archive_memory_count == 1
    assert snap.snapshot_id == snap.snapshot_id


def test_observatory_delta_tracks_growth_archive_and_revival():
    k1 = knowledge("first")
    before = CognitiveObservatory.snapshot(
        project_id="agentmanager",
        captured_at="2026-08-22T04:00:00Z",
        trigger_ref="t0",
        knowledge=(k1,),
        lifecycle=(MemoryLifecycleState(k1.knowledge_id, tier=MemoryTier.ARCHIVE, activation=0.05),),
    )
    k2 = knowledge("second")
    after = CognitiveObservatory.snapshot(
        project_id="agentmanager",
        captured_at="2026-08-22T05:00:00Z",
        trigger_ref="t1",
        knowledge=(k1, k2),
        lifecycle=(
            MemoryLifecycleState(k1.knowledge_id, tier=MemoryTier.WARM, activation=0.7),
            MemoryLifecycleState(k2.knowledge_id, tier=MemoryTier.HOT, activation=0.9),
        ),
    )
    delta = CognitiveObservatory.diff(before, after, annotations=("global_reconciliation",))
    assert delta.added_knowledge_ids == (k2.knowledge_id,)
    assert delta.revived_knowledge_ids == (k1.knowledge_id,)
    assert delta.metric_delta["knowledge_count"] == 1
    assert delta.metric_delta["archive_memory_count"] == -1
    assert delta.annotations == ("global_reconciliation",)


def test_observatory_refuses_cross_project_diff():
    left = CognitiveObservatory.snapshot(project_id="a", captured_at="t", trigger_ref="x")
    right = CognitiveObservatory.snapshot(project_id="b", captured_at="t", trigger_ref="x")
    try:
        CognitiveObservatory.diff(left, right)
    except ValueError as exc:
        assert "different projects" in str(exc)
    else:
        raise AssertionError("cross-project snapshot diff must fail")

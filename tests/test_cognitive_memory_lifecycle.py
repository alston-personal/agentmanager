from datetime import datetime, timedelta, timezone

from agent_core.cognitive_index import (
    AssociationQuery,
    CognitiveAssociationEngine,
    InMemoryCognitiveIndex,
    index_candidates,
)
from agent_core.cognitive_memory_lifecycle import (
    InMemoryLifecycleStore,
    MemoryLifecyclePolicy,
    MemoryLifecycleState,
    MemoryTier,
)
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash


def candidate(statement: str) -> KnowledgeCandidate:
    return KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement=statement,
        confidence=0.9,
        status="validated",
        evidence=(
            EvidenceRef(
                source_kind="test",
                source_ref="test:memory",
                content_hash=evidence_hash(statement),
                trust_class="verified",
            ),
        ),
        metadata={"concepts": ["memory"], "domain": "agent"},
    )


def test_memory_decays_across_tiers_without_deletion():
    policy = MemoryLifecyclePolicy(decay_half_life_days=10)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = MemoryLifecycleState(
        knowledge_id="know_1",
        tier=MemoryTier.HOT,
        activation=1.0,
        last_evaluated_at=start,
    )

    later = policy.decay(state, now=start + timedelta(days=40))

    assert later.knowledge_id == state.knowledge_id
    assert later.activation < state.activation
    assert later.tier in {MemoryTier.COLD, MemoryTier.ARCHIVE}


def test_relevance_can_revive_cold_memory():
    policy = MemoryLifecyclePolicy()
    now = datetime(2026, 8, 21, tzinfo=timezone.utc)
    cold = MemoryLifecycleState(
        knowledge_id="know_old",
        tier=MemoryTier.COLD,
        activation=0.15,
        last_evaluated_at=now,
    )

    revived = policy.reinforce(cold, now=now, relevance=1.0, explicit_recall=True)

    assert revived.activation > cold.activation
    assert revived.tier in {MemoryTier.WARM, MemoryTier.HOT}
    assert revived.access_count == 1


def test_dependencies_keep_memory_from_fading_below_floor():
    policy = MemoryLifecyclePolicy(decay_half_life_days=1, dependency_floor=0.4)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = MemoryLifecycleState(
        knowledge_id="know_dependency",
        activation=0.8,
        dependency_count=3,
        last_evaluated_at=start,
    )

    later = policy.decay(state, now=start + timedelta(days=365))

    assert later.activation >= 0.4
    assert later.tier >= MemoryTier.COOL


def test_archive_is_excluded_from_normal_retrieval_but_explicitly_recallable():
    item = candidate("memory lifecycle should be reversible")
    index = InMemoryCognitiveIndex()
    index_candidates(index, (item,))
    lifecycle = InMemoryLifecycleStore()
    lifecycle.upsert(
        (
            MemoryLifecycleState(
                knowledge_id=item.knowledge_id,
                tier=MemoryTier.ARCHIVE,
                activation=0.05,
            ),
        )
    )
    engine = CognitiveAssociationEngine(index, lifecycle_store=lifecycle)

    normal = engine.retrieve(
        AssociationQuery(text="memory", concepts=frozenset({"memory"})),
        trigger_ref="input:normal",
    )
    recalled = engine.retrieve(
        AssociationQuery(
            text="memory",
            concepts=frozenset({"memory"}),
            include_archive=True,
        ),
        trigger_ref="input:explicit-recall",
    )

    assert item.knowledge_id not in normal.source_ids
    assert item.knowledge_id in recalled.source_ids
    assert "lifecycle_weighted" in recalled.near[0].reasons


def test_cold_memory_ranks_below_hot_equivalent():
    hot = candidate("memory retrieval policy alpha")
    cold = candidate("memory retrieval policy beta")
    index = InMemoryCognitiveIndex()
    index_candidates(index, (hot, cold))
    lifecycle = InMemoryLifecycleStore()
    lifecycle.upsert(
        (
            MemoryLifecycleState(hot.knowledge_id, tier=MemoryTier.HOT, activation=1.0),
            MemoryLifecycleState(cold.knowledge_id, tier=MemoryTier.COLD, activation=0.2),
        )
    )

    result = CognitiveAssociationEngine(index, lifecycle_store=lifecycle).retrieve(
        AssociationQuery(text="memory retrieval policy", concepts=frozenset({"memory"})),
        trigger_ref="input:rank",
    )

    assert result.near[0].knowledge_id == hot.knowledge_id
    scores = {hit.knowledge_id: hit.score for hit in result.near}
    assert scores[hot.knowledge_id] > scores[cold.knowledge_id]

from agent_core.cognitive_index import (
    AssociationQuery,
    CognitiveAssociationEngine,
    InMemoryCognitiveIndex,
    index_candidates,
)
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash


def candidate(project, statement, *, concepts=(), structures=(), domain=None, status="validated"):
    return KnowledgeCandidate(
        project_id=project,
        kind="lesson",
        statement=statement,
        confidence=0.9,
        status=status,
        evidence=(
            EvidenceRef(
                source_kind="test",
                source_ref=f"{project}:{statement[:8]}",
                content_hash=evidence_hash(statement),
                trust_class="verified",
            ),
        ),
        metadata={
            "concepts": list(concepts),
            "structural_signatures": list(structures),
            "domain": domain,
        },
    )


def test_near_retrieval_prefers_shared_terms_and_concepts():
    backend = InMemoryCognitiveIndex()
    auth = candidate(
        "agentmanager",
        "Provider HTTP 403 may be caused by client fingerprint and User-Agent policy",
        concepts=("http", "provider", "user-agent"),
        structures=("input-policy-response",),
        domain="networking",
    )
    other = candidate(
        "language-learning",
        "Spaced repetition should adapt to recall strength",
        concepts=("memory", "learning"),
        structures=("observe-adjust-repeat",),
        domain="education",
    )
    index_candidates(backend, (auth, other))

    result = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(
            text="provider returns HTTP 403",
            concepts=frozenset({"http", "provider"}),
            project_id="agentmanager",
        ),
        trigger_ref="input:test-403",
    )

    assert result.near
    assert result.near[0].knowledge_id == auth.knowledge_id
    assert "shared_concepts" in result.near[0].reasons
    assert result.trigger_ref == "input:test-403"


def test_far_retrieval_finds_cross_domain_structural_analogy():
    backend = InMemoryCognitiveIndex()
    git_merge = candidate(
        "dev-tools",
        "Branches from a common base require conflict detection before merge",
        concepts=("git", "branch"),
        structures=("common-base-parallel-change-merge",),
        domain="source-control",
    )
    same_domain = candidate(
        "agentmanager",
        "Parallel agents also require conflict detection",
        concepts=("agent", "state"),
        structures=("common-base-parallel-change-merge",),
        domain="agent-systems",
    )
    index_candidates(backend, (git_merge, same_domain))

    result = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(
            text="two agents edit state concurrently",
            concepts=frozenset({"agent", "state"}),
            structural_signatures=frozenset({"common-base-parallel-change-merge"}),
            domain="agent-systems",
        ),
        trigger_ref="input:parallel-agent-state",
    )

    assert any(hit.knowledge_id == git_merge.knowledge_id for hit in result.far)
    assert all("shared_structure" in hit.reasons for hit in result.far)
    assert all("cross_domain" in hit.reasons for hit in result.far)
    assert all(hit.knowledge_id != same_domain.knowledge_id for hit in result.far)


def test_superseded_and_rejected_are_excluded_by_default():
    backend = InMemoryCognitiveIndex()
    active = candidate(
        "p",
        "active memory",
        concepts=("memory",),
        domain="agent",
    )
    superseded = candidate(
        "p",
        "old memory",
        concepts=("memory",),
        domain="agent",
        status="superseded",
    )
    index_candidates(backend, (active, superseded))

    result = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(text="memory", concepts=frozenset({"memory"})),
        trigger_ref="input:memory",
    )
    ids = {hit.knowledge_id for hit in result.near}
    assert active.knowledge_id in ids
    assert superseded.knowledge_id not in ids


def test_cross_project_scope_can_be_disabled():
    backend = InMemoryCognitiveIndex()
    local = candidate("p1", "shared state pattern", concepts=("state",), domain="agent")
    remote = candidate("p2", "shared state pattern", concepts=("state",), domain="agent")
    index_candidates(backend, (local, remote))

    result = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(
            text="state",
            concepts=frozenset({"state"}),
            project_id="p1",
            include_cross_project=False,
        ),
        trigger_ref="input:local-only",
    )
    ids = {hit.knowledge_id for hit in result.near}
    assert local.knowledge_id in ids
    assert remote.knowledge_id not in ids


def test_association_set_is_retrieval_only_and_preserves_source_ids():
    backend = InMemoryCognitiveIndex()
    first = candidate("p", "alpha beta", concepts=("alpha",), domain="a")
    second = candidate(
        "q",
        "structural sibling",
        concepts=("other",),
        structures=("feedback-loop",),
        domain="b",
    )
    index_candidates(backend, (first, second))

    result = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(
            text="alpha",
            concepts=frozenset({"alpha"}),
            structural_signatures=frozenset({"feedback-loop"}),
            domain="a",
        ),
        trigger_ref="input:alpha",
    )
    assert result.synthesis_input_refs() == result.source_ids
    assert first.knowledge_id in result.source_ids
    assert second.knowledge_id in result.source_ids

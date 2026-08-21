from agent_core.cognitive_index import (
    AssociationQuery,
    CognitiveAssociationEngine,
    InMemoryCognitiveIndex,
    index_candidates,
)
from agent_core.cognitive_synthesis import CognitiveSynthesisBoundary
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash


def make_candidate(project, statement, *, concepts=(), structures=(), domain=None, relation="supports"):
    return KnowledgeCandidate(
        project_id=project,
        kind="lesson",
        statement=statement,
        confidence=0.9,
        status="validated",
        evidence=(
            EvidenceRef(
                source_kind="test",
                source_ref=f"{project}:{statement[:6]}",
                content_hash=evidence_hash(statement),
                relation=relation,
                trust_class="verified",
            ),
        ),
        metadata={
            "concepts": list(concepts),
            "structural_signatures": list(structures),
            "domain": domain,
        },
    )


def test_synthesis_envelope_contains_near_and_far_sources():
    near = make_candidate("agentmanager", "agent state conflict", concepts=("state",), domain="agents")
    far = make_candidate(
        "git",
        "branch conflict from common base",
        concepts=("branch",),
        structures=("common-base-parallel-change-merge",),
        domain="source-control",
    )
    store = {item.knowledge_id: item for item in (near, far)}
    backend = InMemoryCognitiveIndex()
    index_candidates(backend, (near, far))
    associations = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(
            text="state conflict",
            concepts=frozenset({"state"}),
            structural_signatures=frozenset({"common-base-parallel-change-merge"}),
            domain="agents",
        ),
        trigger_ref="input:new-conflict",
    )

    envelope = CognitiveSynthesisBoundary(store.get).build_envelope(
        associations,
        trigger_text="How should parallel agents merge state?",
        project_id="agentmanager",
        synthesis_kind="brainstorm",
    )
    assert near.knowledge_id in envelope.source_ids
    assert far.knowledge_id in envelope.source_ids
    assert "output_is_candidate_not_fact" in envelope.required_rules


def test_model_cannot_self_promote_synthesized_output():
    source = make_candidate("agentmanager", "source lesson", concepts=("lesson",), domain="agents")
    store = {source.knowledge_id: source}
    backend = InMemoryCognitiveIndex()
    index_candidates(backend, (source,))
    associations = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(text="lesson", concepts=frozenset({"lesson"})),
        trigger_ref="input:new",
    )
    boundary = CognitiveSynthesisBoundary(store.get)
    envelope = boundary.build_envelope(
        associations,
        trigger_text="new input",
        project_id="agentmanager",
    )
    proposed = KnowledgeCandidate(
        project_id="other",
        kind="insight",
        statement="Novel synthesized insight",
        confidence=0.99,
        status="validated",
        abstraction_level="cross_project",
    )

    normalized = boundary.normalize_candidate(envelope, proposed)
    assert normalized.project_id == "agentmanager"
    assert normalized.status == "candidate"
    assert normalized.abstraction_level == "working"
    assert source.knowledge_id in normalized.derived_from
    assert normalized.metadata["governance_state"] == "candidate"


def test_contradicting_source_evidence_survives_resynthesis():
    supporting = make_candidate("p", "supports idea", concepts=("idea",), domain="a")
    contradicting = make_candidate(
        "q",
        "contradicts idea",
        concepts=("idea",),
        domain="b",
        relation="contradicts",
    )
    store = {item.knowledge_id: item for item in (supporting, contradicting)}
    backend = InMemoryCognitiveIndex()
    index_candidates(backend, (supporting, contradicting))
    associations = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(text="idea", concepts=frozenset({"idea"})),
        trigger_ref="input:idea",
    )
    boundary = CognitiveSynthesisBoundary(store.get)
    envelope = boundary.build_envelope(
        associations,
        trigger_text="reconsider idea",
        project_id="p",
    )
    proposed = KnowledgeCandidate(project_id="p", kind="insight", statement="reconsidered idea")
    normalized = boundary.normalize_candidate(envelope, proposed)
    assert any(item.relation == "contradicts" for item in normalized.evidence)


def test_record_rejects_candidate_missing_lineage():
    source = make_candidate("p", "source", concepts=("source",), domain="a")
    store = {source.knowledge_id: source}
    backend = InMemoryCognitiveIndex()
    index_candidates(backend, (source,))
    associations = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(text="source", concepts=frozenset({"source"})),
        trigger_ref="input:source",
    )
    boundary = CognitiveSynthesisBoundary(store.get)
    envelope = boundary.build_envelope(
        associations,
        trigger_text="source",
        project_id="p",
    )
    bad = KnowledgeCandidate(project_id="p", kind="insight", statement="bad")
    try:
        boundary.record(envelope, (bad,))
    except ValueError as exc:
        assert "provenance" in str(exc)
    else:
        raise AssertionError("expected missing provenance rejection")


def test_governed_candidate_can_be_recorded():
    source = make_candidate("p", "source", concepts=("source",), domain="a")
    store = {source.knowledge_id: source}
    backend = InMemoryCognitiveIndex()
    index_candidates(backend, (source,))
    associations = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(text="source", concepts=frozenset({"source"})),
        trigger_ref="input:source",
    )
    boundary = CognitiveSynthesisBoundary(store.get)
    envelope = boundary.build_envelope(
        associations,
        trigger_text="source",
        project_id="p",
    )
    proposed = KnowledgeCandidate(project_id="p", kind="insight", statement="new insight")
    normalized = boundary.normalize_candidate(envelope, proposed)
    record = boundary.record(envelope, (normalized,))
    assert record.trigger_ref == "input:source"
    assert record.candidates[0].status == "candidate"

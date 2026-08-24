from runtime_core.cognitive_ir import (
    EvidenceRef,
    KnowledgeCandidate,
    SynthesisRecord,
    contradiction_refs,
    evidence_hash,
    merge_evidence,
)


def evidence(ref, content, relation="supports", trust="verified"):
    return EvidenceRef(
        source_kind="conversation",
        source_ref=ref,
        content_hash=evidence_hash(content),
        relation=relation,
        trust_class=trust,
    )


def test_knowledge_candidate_is_content_addressed():
    ev = evidence("chatgpt:1", "project state must not belong to a session")
    a = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture_principle",
        statement="Project owns state; sessions do not.",
        evidence=(ev,),
    )
    b = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture_principle",
        statement="Project owns state; sessions do not.",
        evidence=(ev,),
    )
    assert a.knowledge_id == b.knowledge_id


def test_contradicting_evidence_is_retained_not_summarized_away():
    supports = evidence("gemini:2", "SQLite is sufficient for the present workload")
    contradicts = evidence(
        "codex:9",
        "Concurrent write load may require PostgreSQL",
        relation="contradicts",
    )
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="decision_candidate",
        statement="Use SQLite for the current workload.",
        confidence=0.78,
        evidence=(supports, contradicts),
    )
    assert candidate.contradiction_count == 1
    assert contradiction_refs(candidate) == (contradicts,)


def test_merge_evidence_deduplicates_without_erasing_relation():
    same_support = evidence("chatgpt:3", "State Kernel is the authority")
    contradiction = EvidenceRef(
        source_kind=same_support.source_kind,
        source_ref=same_support.source_ref,
        content_hash=same_support.content_hash,
        relation="contradicts",
        trust_class=same_support.trust_class,
    )
    merged = merge_evidence((same_support,), (same_support, contradiction))
    assert len(merged) == 2
    assert {item.relation for item in merged} == {"supports", "contradicts"}


def test_new_input_can_create_new_synthesis_from_prior_synthesis_refs():
    old = KnowledgeCandidate(
        project_id="agentmanager",
        kind="principle",
        statement="Do not rebuild mature protocol layers.",
        evidence=(evidence("chatgpt:4", "reuse ACP MCP A2A"),),
    )
    new = KnowledgeCandidate(
        project_id="agentmanager",
        kind="meta_principle",
        statement="Own differentiated semantics; adapt commodity infrastructure.",
        abstraction_level="cross_project",
        confidence=0.66,
        evidence=(evidence("user:5", "do not rebuild wheels"),),
        derived_from=(old.knowledge_id,),
    )
    synthesis = SynthesisRecord(
        project_id="agentmanager",
        input_refs=(old.knowledge_id,),
        trigger_ref="user:5",
        candidates=(new,),
        synthesis_kind="brainstorm",
    )
    assert synthesis.synthesis_id.startswith("syn_")
    assert synthesis.candidates[0].derived_from == (old.knowledge_id,)


def test_superseded_knowledge_keeps_explicit_lineage():
    old = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture",
        statement="Each device runs a full runtime.",
        status="superseded",
        evidence=(evidence("history:1", "old architecture"),),
    )
    current = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture",
        statement="Devices use lightweight edges against a shared Core.",
        status="validated",
        confidence=0.95,
        evidence=(evidence("production:1", "distributed core E2E succeeded"),),
        supersedes=(old.knowledge_id,),
    )
    assert current.supersedes == (old.knowledge_id,)
    assert old.status == "superseded"


def test_cross_project_candidate_is_not_automatically_validated():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="analogy",
        statement="Durable state should be separated from transient platforms.",
        abstraction_level="cross_project",
        confidence=0.6,
        evidence=(evidence("synthesis:1", "cross-domain analogy"),),
    )
    assert candidate.status == "candidate"

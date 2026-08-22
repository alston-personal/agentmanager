from agent_core.cognitive_promotion import CognitivePromotionPolicy
from agent_core.governance_registry import GovernanceRegistry
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash


def ev(kind, ref, text, *, relation="supports", trust="verified"):
    return EvidenceRef(
        source_kind=kind,
        source_ref=ref,
        content_hash=evidence_hash(text),
        relation=relation,
        trust_class=trust,
    )


def test_working_memory_does_not_need_durable_promotion_authority():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="observation",
        statement="A temporary implementation idea.",
    )
    decision = CognitivePromotionPolicy(
        governance_registry=GovernanceRegistry()
    ).evaluate(candidate, "working")
    assert decision.allowed is True


def test_project_promotion_requires_verified_evidence():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement="Explicit User-Agent can avoid some WAF client-fingerprint blocks.",
        confidence=0.9,
        evidence=(ev("production", "provider-probe", "explicit UA probe succeeded"),),
    )
    policy = CognitivePromotionPolicy()
    allowed = policy.evaluate(candidate, "project")
    assert allowed.allowed is True
    promoted = policy.promote(candidate, "project")
    assert promoted.status == "validated"
    assert promoted.abstraction_level == "project"
    assert promoted.knowledge_id != candidate.knowledge_id
    assert candidate.knowledge_id in promoted.derived_from
    assert candidate.knowledge_id in promoted.supersedes


def test_caller_cannot_mint_promotion_authority_when_registry_lacks_capability():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement="Verified lesson without registered durable authority.",
        confidence=0.9,
        evidence=(ev("test", "e1", "verified"),),
    )
    policy = CognitivePromotionPolicy(governance_registry=GovernanceRegistry())
    decision = policy.evaluate(candidate, "project")
    assert decision.allowed is False
    assert "governance:unknown_capability" in decision.reasons


def test_cross_project_requires_two_independent_verified_sources():
    one_source = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture_principle",
        statement="Durable state should not belong to transient sessions.",
        confidence=0.92,
        evidence=(ev("project", "agentmanager", "session independence"),),
    )
    decision = CognitivePromotionPolicy().evaluate(one_source, "cross_project")
    assert decision.allowed is False
    assert "cross-project memory requires at least two independent verified sources" in decision.reasons


def test_cross_project_promotion_succeeds_with_independent_evidence_and_registry_authority():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture_principle",
        statement="Durable identity/state should be separated from transient platform/runtime.",
        confidence=0.9,
        evidence=(
            ev("project", "agentmanager", "AgentOS session-independent state"),
            ev("project", "chamber", "content ownership separate from platform"),
        ),
    )
    decision = CognitivePromotionPolicy().evaluate(candidate, "cross_project")
    assert decision.allowed is True
    assert decision.independent_support_count == 2

    promoted = CognitivePromotionPolicy().promote(candidate, "cross_project")
    assert candidate.knowledge_id in promoted.derived_from
    assert candidate.knowledge_id in promoted.supersedes


def test_unreviewed_contradiction_blocks_promotion_but_is_not_deleted():
    contradiction = ev(
        "review",
        "review-2",
        "counterexample",
        relation="contradicts",
    )
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement="Use SQLite for all future workloads.",
        confidence=0.9,
        evidence=(
            ev("test", "load-1", "SQLite passed current workload"),
            contradiction,
        ),
    )
    decision = CognitivePromotionPolicy().evaluate(candidate, "project")
    assert decision.allowed is False
    assert "contradictory evidence exists and has not been reviewed" in decision.reasons
    assert candidate.contradiction_count == 1


def test_reviewed_contradiction_can_promote_while_evidence_remains():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="decision",
        statement="SQLite is appropriate for the current workload, with an upgrade trigger.",
        confidence=0.85,
        evidence=(
            ev("test", "load-1", "SQLite passed current workload"),
            ev("review", "scale-risk", "write contention may require PostgreSQL", relation="contradicts"),
        ),
        metadata={"contradictions_reviewed": True, "upgrade_trigger": "write contention"},
    )
    promoted = CognitivePromotionPolicy().promote(candidate, "project")
    assert promoted.status == "validated"
    assert promoted.contradiction_count == 1


def test_noop_promotion_does_not_create_self_lineage():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement="already project memory",
        abstraction_level="project",
        status="validated",
        confidence=0.9,
        evidence=(ev("test", "e1", "verified"),),
    )
    result = CognitivePromotionPolicy().promote(candidate, "project")
    assert result is candidate
    assert candidate.knowledge_id not in result.derived_from
    assert candidate.knowledge_id not in result.supersedes

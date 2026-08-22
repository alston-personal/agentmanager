from agent_core.cognitive_promotion import CognitivePromotionPolicy
from agent_core.governance import CapabilityLevel, RiskDimensions, required_controls
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash


def ev(kind, ref, text, *, relation="supports", trust="verified"):
    return EvidenceRef(
        source_kind=kind,
        source_ref=ref,
        content_hash=evidence_hash(text),
        relation=relation,
        trust_class=trust,
    )


def project_controls():
    risks = RiskDimensions(authority=3, persistence=3, propagation=2, uncertainty=3)
    return required_controls(
        CapabilityLevel.COMMIT,
        effects={"durable_memory"},
        risks=risks,
    )


def cross_project_controls():
    risks = RiskDimensions(authority=3, persistence=5, propagation=5, uncertainty=3)
    return required_controls(
        CapabilityLevel.COMMIT,
        effects={"durable_memory", "cross_project"},
        risks=risks,
    )


def test_working_memory_does_not_need_durable_promotion_controls():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="observation",
        statement="A temporary implementation idea.",
    )
    decision = CognitivePromotionPolicy().evaluate(candidate, "working")
    assert decision.allowed is True


def test_project_promotion_requires_verified_evidence_and_governance():
    candidate = KnowledgeCandidate(
        project_id="agentmanager",
        kind="lesson",
        statement="Explicit User-Agent can avoid some WAF client-fingerprint blocks.",
        confidence=0.9,
        evidence=(ev("production", "provider-probe", "explicit UA probe succeeded"),),
    )
    policy = CognitivePromotionPolicy()
    denied = policy.evaluate(candidate, "project")
    assert denied.allowed is False
    assert any(reason.startswith("governance:") for reason in denied.reasons)

    allowed = policy.evaluate(candidate, "project", governance_controls=project_controls())
    assert allowed.allowed is True
    promoted = policy.promote(candidate, "project", governance_controls=project_controls())
    assert promoted.status == "validated"
    assert promoted.abstraction_level == "project"
    assert promoted.knowledge_id != candidate.knowledge_id
    assert candidate.knowledge_id in promoted.derived_from
    assert candidate.knowledge_id in promoted.supersedes


def test_cross_project_requires_two_independent_verified_sources():
    one_source = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture_principle",
        statement="Durable state should not belong to transient sessions.",
        confidence=0.92,
        evidence=(ev("project", "agentmanager", "session independence"),),
    )
    decision = CognitivePromotionPolicy().evaluate(
        one_source,
        "cross_project",
        governance_controls=cross_project_controls(),
    )
    assert decision.allowed is False
    assert "cross-project memory requires at least two independent verified sources" in decision.reasons


def test_cross_project_promotion_succeeds_with_independent_evidence_and_controls():
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
    controls = cross_project_controls()
    decision = CognitivePromotionPolicy().evaluate(
        candidate, "cross_project", governance_controls=controls
    )
    assert decision.allowed is True
    assert decision.independent_support_count == 2
    assert "independent_verification" in controls

    promoted = CognitivePromotionPolicy().promote(
        candidate, "cross_project", governance_controls=controls
    )
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
    decision = CognitivePromotionPolicy().evaluate(
        candidate, "project", governance_controls=project_controls()
    )
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
    promoted = CognitivePromotionPolicy().promote(
        candidate, "project", governance_controls=project_controls()
    )
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
    result = CognitivePromotionPolicy().promote(
        candidate, "project", governance_controls=project_controls()
    )
    assert result is candidate
    assert candidate.knowledge_id not in result.derived_from
    assert candidate.knowledge_id not in result.supersedes

from agent_core.cognitive_index import (
    AssociationQuery,
    CognitiveAssociationEngine,
    InMemoryCognitiveIndex,
    index_candidates,
)
from agent_core.cognitive_promotion import CognitivePromotionPolicy
from agent_core.cognitive_refresh import CognitiveRefreshPlanner, SynthesisDependencyIndex
from agent_core.cognitive_synthesis import CognitiveSynthesisBoundary
from agent_core.experience_compiler import ExperienceCompilerBoundary
from agent_core.governance import CapabilityLevel, RiskDimensions, required_controls
from runtime_core.cognitive_ir import KnowledgeCandidate
from runtime_core.experience_ir import ExperienceBatch, ExperienceEvent


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


def event(project, source_ref, content):
    return ExperienceEvent(
        project_id=project,
        source_kind="conversation",
        source_ref=source_ref,
        actor_kind="human_agent_pair",
        event_kind="discussion",
        content=content,
        occurred_at="2026-08-21T12:00:00Z",
        trust_class="verified",
    )


def compile_project_memory(project, source_event, statement, *, concepts, structures, domain):
    batch = ExperienceBatch(
        project_id=project,
        events=(source_event,),
        source_window_ref=f"window:{project}",
    )
    compiler = ExperienceCompilerBoundary()
    envelope = compiler.build_envelope(batch)
    proposed = KnowledgeCandidate(
        project_id=project,
        kind="architecture_lesson",
        statement=statement,
        confidence=0.9,
        metadata={
            "concepts": list(concepts),
            "structural_signatures": list(structures),
            "domain": domain,
        },
    )
    working = compiler.normalize_candidate(
        envelope,
        proposed,
        supporting_event_ids=(source_event.event_id,),
    )
    return CognitivePromotionPolicy().promote(
        working,
        "project",
        governance_controls=project_controls(),
    )


def test_full_cognitive_compounding_loop():
    # 1. Two distributed project discussions become governed project memories.
    agent_event = event(
        "agentmanager",
        "chat:agentmanager",
        "Project state must survive model, IDE and conversation changes.",
    )
    chamber_event = event(
        "chamber",
        "chat:chamber",
        "Content ownership must survive the platform that currently hosts it.",
    )

    agent_memory = compile_project_memory(
        "agentmanager",
        agent_event,
        "Durable project state should be separated from transient model/session/runtime.",
        concepts=("durable-ownership", "state"),
        structures=("durable-core-transient-host",),
        domain="agent-systems",
    )
    chamber_memory = compile_project_memory(
        "chamber",
        chamber_event,
        "Durable content identity should be separated from transient hosting platform.",
        concepts=("durable-ownership", "content"),
        structures=("durable-core-transient-host",),
        domain="content-platforms",
    )

    assert agent_event.event_id in agent_memory.derived_from
    assert chamber_event.event_id in chamber_memory.derived_from

    # 2. Indexing finds both direct conceptual relevance and a cross-domain
    # structural analogy without owning a vector database.
    memories = {item.knowledge_id: item for item in (agent_memory, chamber_memory)}
    backend = InMemoryCognitiveIndex()
    index_candidates(backend, tuple(memories.values()))
    associations = CognitiveAssociationEngine(backend).retrieve(
        AssociationQuery(
            text="What should own durable identity when execution platforms change?",
            concepts=frozenset({"durable-ownership"}),
            structural_signatures=frozenset({"durable-core-transient-host"}),
            domain="architecture",
            include_cross_project=True,
        ),
        trigger_ref="input:ownership-generalization",
    )
    assert agent_memory.knowledge_id in associations.source_ids
    assert chamber_memory.knowledge_id in associations.source_ids
    assert len(associations.far) == 2

    # 3. An external synthesizer may propose a novel generalization, but the
    # boundary forcibly returns it to Working/candidate and attaches all lineage.
    boundary = CognitiveSynthesisBoundary(memories.get)
    synthesis_envelope = boundary.build_envelope(
        associations,
        trigger_text="Generalize the common architecture principle.",
        project_id="agentmanager",
        synthesis_kind="cross_project",
    )
    model_proposal = KnowledgeCandidate(
        project_id="agentmanager",
        kind="architecture_principle",
        statement="Durable ownership should belong to a stable identity/state layer, not its transient execution or hosting platform.",
        confidence=0.92,
        status="validated",  # malicious/overconfident self-promotion attempt
        abstraction_level="cross_project",
        metadata={
            "concepts": ["durable-ownership", "platform-independence"],
            "structural_signatures": ["durable-core-transient-host"],
            "domain": "architecture",
        },
    )
    working_insight = boundary.normalize_candidate(synthesis_envelope, model_proposal)
    assert working_insight.status == "candidate"
    assert working_insight.abstraction_level == "working"
    assert set((agent_memory.knowledge_id, chamber_memory.knowledge_id)) <= set(
        working_insight.derived_from
    )

    record = boundary.record(synthesis_envelope, (working_insight,))

    # 4. Only the separate evidence+governance promotion gate may turn the
    # synthesis into reusable L3 knowledge.
    cross_project = CognitivePromotionPolicy().promote(
        working_insight,
        "cross_project",
        governance_controls=cross_project_controls(),
    )
    assert cross_project.status == "validated"
    assert cross_project.abstraction_level == "cross_project"
    assert working_insight.knowledge_id in cross_project.supersedes

    # 5. Later contradictory input does not rewrite the insight. It schedules
    # reconsideration of the synthesis that created it.
    dependencies = SynthesisDependencyIndex()
    dependencies.register(record)
    contradiction = KnowledgeCandidate(
        project_id="agentmanager",
        kind="counterexample",
        statement="Some regulated platforms may themselves be the legally authoritative identity layer.",
        confidence=0.8,
        metadata={
            "contradicts_knowledge_ids": [agent_memory.knowledge_id],
            "concepts": ["durable-ownership"],
        },
    )
    refresh = CognitiveRefreshPlanner(dependencies).plan(
        contradiction,
        associations,
    )
    assert refresh
    assert "new_contradiction" in refresh[0].reasons
    assert record.synthesis_id == refresh[0].synthesis_id

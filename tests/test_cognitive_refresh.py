from agent_core.cognitive_index import AssociationHit, AssociationQuery, AssociationSet
from agent_core.cognitive_refresh import CognitiveRefreshPlanner, SynthesisDependencyIndex
from runtime_core.cognitive_ir import KnowledgeCandidate, SynthesisRecord


def knowledge(project, statement, *, derived_from=(), supersedes=(), metadata=None):
    return KnowledgeCandidate(
        project_id=project,
        kind="insight",
        statement=statement,
        confidence=0.8,
        derived_from=tuple(derived_from),
        supersedes=tuple(supersedes),
        metadata=metadata or {},
    )


def synthesis(project, source_ids, statement="synthesis"):
    candidate = knowledge(project, statement, derived_from=source_ids)
    return SynthesisRecord(
        project_id=project,
        input_refs=tuple(source_ids),
        candidates=(candidate,),
        trigger_ref="input:old",
        synthesis_kind="incremental",
    )


def associations(*ids, far_ids=()):
    far_ids = set(far_ids)
    near = tuple(
        AssociationHit(knowledge_id=item, mode="near", score=0.8, reasons=("shared_terms",))
        for item in ids
        if item not in far_ids
    )
    far = tuple(
        AssociationHit(knowledge_id=item, mode="far", score=0.9, reasons=("shared_structure", "cross_domain"))
        for item in ids
        if item in far_ids
    )
    return AssociationSet(
        trigger_ref="input:new",
        query=AssociationQuery(text="new input"),
        near=near,
        far=far,
        source_ids=tuple(ids),
    )


def test_superseded_source_triggers_high_priority_resynthesis():
    old = knowledge("p", "old")
    record = synthesis("p", (old.knowledge_id,))
    deps = SynthesisDependencyIndex()
    deps.register(record)
    new = knowledge("p", "replacement", supersedes=(old.knowledge_id,))

    requests = CognitiveRefreshPlanner(deps).plan(new, associations(old.knowledge_id))
    assert len(requests) == 1
    assert "source_superseded" in requests[0].reasons
    assert old.knowledge_id in requests[0].affected_source_ids
    assert requests[0].priority >= 50


def test_new_contradiction_has_strongest_refresh_signal():
    source = knowledge("p", "claim")
    record = synthesis("p", (source.knowledge_id,))
    deps = SynthesisDependencyIndex()
    deps.register(record)
    contradiction = knowledge(
        "p",
        "counter evidence",
        metadata={"contradicts_knowledge_ids": [source.knowledge_id]},
    )

    requests = CognitiveRefreshPlanner(deps).plan(
        contradiction,
        associations(source.knowledge_id),
    )
    assert len(requests) == 1
    assert "new_contradiction" in requests[0].reasons
    assert requests[0].priority >= 60


def test_new_far_analogy_can_enrich_existing_synthesis():
    source = knowledge("p", "agent merge")
    far = knowledge("git", "branch merge")
    record = synthesis("p", (source.knowledge_id,))
    deps = SynthesisDependencyIndex()
    deps.register(record)

    # Make the new far source itself derive from the existing source so the
    # dependency graph knows the existing synthesis is relevant to the new hit.
    far_trigger = knowledge("git", "branch merge analogy", derived_from=(source.knowledge_id,))
    result = associations(source.knowledge_id, far.knowledge_id, far_ids=(far.knowledge_id,))

    requests = CognitiveRefreshPlanner(deps).plan(far_trigger, result)
    assert len(requests) == 1
    assert "new_association" in requests[0].reasons
    assert "new_structural_analogy" in requests[0].reasons
    assert far.knowledge_id in requests[0].newly_associated_ids


def test_irrelevant_new_input_does_not_churn_synthesis_graph():
    source = knowledge("p", "source")
    unrelated = knowledge("q", "unrelated")
    record = synthesis("p", (source.knowledge_id,))
    deps = SynthesisDependencyIndex()
    deps.register(record)

    requests = CognitiveRefreshPlanner(deps).plan(unrelated, associations(unrelated.knowledge_id))
    assert requests == ()


def test_dependency_index_tracks_candidate_lineage_too():
    root = knowledge("p", "root")
    indirect = knowledge("p", "derived", derived_from=(root.knowledge_id,))
    record = SynthesisRecord(
        project_id="p",
        input_refs=(indirect.knowledge_id,),
        candidates=(indirect,),
        trigger_ref="input:old",
    )
    deps = SynthesisDependencyIndex()
    deps.register(record)
    assert record.synthesis_id in deps.dependent_syntheses((root.knowledge_id,))

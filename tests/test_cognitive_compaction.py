from agent_core.cognitive_compaction import CognitiveCompactionPlanner, KnowledgeLineageResolver
from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, evidence_hash


def candidate(project, statement, *, level="project", confidence=0.9, derived_from=(), concepts=(), status="validated"):
    return KnowledgeCandidate(
        project_id=project,
        kind="lesson",
        statement=statement,
        abstraction_level=level,
        confidence=confidence,
        status=status,
        derived_from=tuple(derived_from),
        evidence=(
            EvidenceRef(
                source_kind="test",
                source_ref=f"{project}:{statement[:6]}",
                content_hash=evidence_hash(statement),
                trust_class="verified",
            ),
        ),
        metadata={"concepts": list(concepts)},
    )


def test_lineage_resolves_back_to_experience_events():
    first = candidate("p", "first", derived_from=("exp_aaa",))
    second = candidate("p", "second", derived_from=(first.knowledge_id, "exp_bbb"))
    store = {item.knowledge_id: item for item in (first, second)}
    experience, external = KnowledgeLineageResolver(store.get).roots((second.knowledge_id,))
    assert experience == ("exp_aaa", "exp_bbb")
    assert external == ()


def test_lineage_uses_evidence_anchor_when_no_explicit_parent():
    root = candidate("p", "root")
    store = {root.knowledge_id: root}
    experience, external = KnowledgeLineageResolver(store.get).roots((root.knowledge_id,))
    assert experience == ()
    assert len(external) == 1
    assert external[0].startswith("test:")


def test_lineage_cycle_fails_closed():
    # Construct an artificial lookup cycle using object replacement through a mapping.
    a = candidate("p", "a", derived_from=("know_b",))
    b = candidate("p", "b", derived_from=("know_a",))
    mapping = {"know_a": a, "know_b": b}
    try:
        KnowledgeLineageResolver(mapping.get).roots(("know_a",))
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("expected lineage cycle rejection")


def test_project_compaction_uses_validated_project_knowledge_only():
    a = candidate("p", "a", derived_from=("exp_a",))
    b = candidate("p", "b", derived_from=("exp_b",))
    working = candidate("p", "working", level="working", derived_from=("exp_w",))
    rejected = candidate("p", "rejected", derived_from=("exp_r",), status="rejected")
    other = candidate("q", "other", derived_from=("exp_q",))
    values = (a, b, working, rejected, other)
    store = {item.knowledge_id: item for item in values}

    plans = CognitiveCompactionPlanner(store.get).plan_project_compaction(values, project_id="p")
    assert len(plans) == 1
    assert set(plans[0].source_knowledge_ids) == {a.knowledge_id, b.knowledge_id}
    assert plans[0].root_experience_ids == ("exp_a", "exp_b")


def test_cross_project_meta_synthesis_requires_shared_concept_across_projects():
    a = candidate(
        "agentmanager",
        "state belongs to project",
        level="cross_project",
        derived_from=("exp_a",),
        concepts=("state-ownership",),
    )
    b = candidate(
        "chamber",
        "content ownership should be platform independent",
        level="cross_project",
        derived_from=("exp_b",),
        concepts=("state-ownership",),
    )
    c = candidate(
        "language",
        "spaced repetition",
        level="cross_project",
        derived_from=("exp_c",),
        concepts=("learning",),
    )
    values = (a, b, c)
    store = {item.knowledge_id: item for item in values}

    plans = CognitiveCompactionPlanner(store.get).plan_cross_project(values)
    assert len(plans) == 1
    assert plans[0].synthesis_kind == "cross_project"
    assert set(plans[0].source_knowledge_ids) == {a.knowledge_id, b.knowledge_id}
    assert "state-ownership" in plans[0].reason

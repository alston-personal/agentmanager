from agent_core.experience_compiler import (
    ExperienceCompilerBoundary,
    group_events_for_compaction,
)
from runtime_core.cognitive_ir import KnowledgeCandidate
from runtime_core.experience_ir import ExperienceBatch, ExperienceEvent


def event(content, *, project="p", source="chatgpt", ref=None, trust="observed"):
    return ExperienceEvent(
        project_id=project,
        source_kind=source,
        source_ref=ref or f"{source}:{content[:6]}",
        actor_kind="agent",
        event_kind="message",
        content=content,
        occurred_at="2026-08-21T12:00:00Z",
        trust_class=trust,
    )


def test_experience_event_is_content_addressed_and_source_neutral():
    first = event("same content", source="chatgpt", ref="chat:1")
    second = event("same content", source="gemini", ref="gemini:1")
    assert first.event_id != second.event_id
    assert first.content_hash == second.content_hash


def test_batch_requires_one_project():
    try:
        ExperienceBatch(
            project_id="p1",
            events=(event("a", project="p1"), event("b", project="p2")),
            source_window_ref="window:1",
        )
    except ValueError as exc:
        assert "share project_id" in str(exc)
    else:
        raise AssertionError("expected project mismatch rejection")


def test_compiler_forces_extracted_knowledge_back_to_candidate():
    source = event("We decided to use a State Kernel after finding latest-task-wins races.")
    batch = ExperienceBatch(project_id="p", events=(source,), source_window_ref="window:1")
    boundary = ExperienceCompilerBoundary()
    envelope = boundary.build_envelope(batch)
    proposed = KnowledgeCandidate(
        project_id="wrong",
        kind="decision",
        statement="Use State Kernel instead of latest-task-wins",
        status="validated",
        abstraction_level="cross_project",
        confidence=0.95,
    )
    normalized = boundary.normalize_candidate(
        envelope,
        proposed,
        supporting_event_ids=(source.event_id,),
    )
    assert normalized.project_id == "p"
    assert normalized.status == "candidate"
    assert normalized.abstraction_level == "working"
    assert source.event_id in normalized.derived_from
    assert normalized.evidence[0].source_ref == source.source_ref
    assert normalized.metadata["compiled_from_experience"] is True


def test_compiler_rejects_unknown_or_missing_support():
    source = event("source")
    batch = ExperienceBatch(project_id="p", events=(source,), source_window_ref="window:1")
    boundary = ExperienceCompilerBoundary()
    envelope = boundary.build_envelope(batch)
    proposed = KnowledgeCandidate(project_id="p", kind="lesson", statement="lesson")

    for ids in ((), ("exp_missing",)):
        try:
            boundary.normalize_candidate(envelope, proposed, supporting_event_ids=ids)
        except ValueError:
            pass
        else:
            raise AssertionError("expected unsupported extraction rejection")


def test_compaction_batches_are_bounded_and_stable():
    events = tuple(event(f"event {index}", ref=f"chat:{index}") for index in range(5))
    batches = group_events_for_compaction(events, max_events=2)
    assert [len(item) for item in batches] == [2, 2, 1]
    assert batches[0][0].source_ref == "chat:0"


def test_compilation_envelope_exposes_explicit_extraction_rules():
    source = event("hypothesis")
    batch = ExperienceBatch(project_id="p", events=(source,), source_window_ref="window:1")
    envelope = ExperienceCompilerBoundary().build_envelope(batch)
    assert "distinguish_observation_from_inference" in envelope.rules
    assert "failure" in envelope.required_output_kinds
    assert "lesson" in envelope.required_output_kinds

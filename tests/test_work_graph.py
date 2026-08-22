from dataclasses import replace

from agent_core.work_graph import InMemoryWorkGraph
from runtime_core.work_v1 import WorkItem


def work(instruction, *, base="state_head", priority=0, status="pending", depends_on=()):
    return WorkItem(
        project_id="agentmanager",
        base_state_id=base,
        instruction=instruction,
        capability="agent.reason",
        priority=priority,
        status=status,
        depends_on=tuple(depends_on),
        acceptance_criteria=("tests pass",),
        created_by="test",
    )


def test_work_identity_is_stable_across_status_and_priority_changes():
    item = work("Implement Work Graph", priority=10, status="pending")
    assert replace(item, status="ready").work_id == item.work_id
    assert replace(item, status="running").work_id == item.work_id
    assert replace(item, priority=999).work_id == item.work_id


def test_continue_prefers_highest_priority_ready_work_on_current_head():
    graph = InMemoryWorkGraph()
    low = work("Low priority", priority=1)
    high = work("High priority", priority=10)
    graph.add((low, high))

    decision = graph.select_continue(project_id="agentmanager", head_state_id="state_head")
    assert decision.work_id == high.work_id
    assert decision.reason == "highest_priority_ready_at_head"
    assert decision.stale_base is False


def test_dependencies_block_until_predecessor_is_done():
    graph = InMemoryWorkGraph()
    first = work("Foundation", priority=1)
    second = work("Dependent", priority=100, depends_on=(first.work_id,))
    graph.add((first, second))

    assert graph.select_continue(project_id="agentmanager", head_state_id="state_head").work_id == first.work_id
    first = graph.transition(first.work_id, "ready", reason="deps clear", actor_ref="scheduler")
    first = graph.transition(first.work_id, "running", reason="start", actor_ref="worker")
    first = graph.transition(first.work_id, "done", reason="accepted", actor_ref="validator")
    assert first.status == "done"

    decision = graph.select_continue(project_id="agentmanager", head_state_id="state_head")
    assert decision.work_id == second.work_id


def test_current_head_work_beats_higher_priority_stale_work():
    graph = InMemoryWorkGraph()
    current = work("Current state task", base="state_new", priority=1)
    stale = work("Old high priority task", base="state_old", priority=999)
    graph.add((current, stale))

    decision = graph.select_continue(project_id="agentmanager", head_state_id="state_new")
    assert decision.work_id == current.work_id
    assert decision.stale_base is False


def test_stale_work_is_explicit_when_it_is_only_candidate():
    graph = InMemoryWorkGraph()
    stale = work("Needs rebase", base="state_old", priority=5)
    graph.add((stale,))

    decision = graph.select_continue(project_id="agentmanager", head_state_id="state_new")
    assert decision.work_id == stale.work_id
    assert decision.stale_base is True
    assert decision.reason == "stale_base_requires_rebase_or_validation"


def test_work_dependency_cycle_fails_closed():
    a = work("A")
    b = work("B", depends_on=(a.work_id,))
    # Rebuild A with a dependency on B. Because dependency identity participates
    # in work identity, use a graph-level explicit malformed pair through replace.
    a_cycle = replace(a, depends_on=(b.work_id,))
    graph = InMemoryWorkGraph()
    try:
        graph.add((a_cycle, b))
    except ValueError as exc:
        assert "unknown work dependency" in str(exc) or "cycle" in str(exc)
    else:
        raise AssertionError("dependency cycle/dangling identity must fail closed")


def test_invalid_terminal_transition_is_rejected():
    graph = InMemoryWorkGraph()
    item = work("Terminal")
    graph.add((item,))
    graph.transition(item.work_id, "ready", reason="ready", actor_ref="scheduler")
    graph.transition(item.work_id, "running", reason="start", actor_ref="worker")
    graph.transition(item.work_id, "done", reason="accepted", actor_ref="validator")
    try:
        graph.transition(item.work_id, "running", reason="retry", actor_ref="worker")
    except ValueError as exc:
        assert "invalid work transition" in str(exc)
    else:
        raise AssertionError("done work must be terminal")

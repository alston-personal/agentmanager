from runtime_core.canonical_ir import CanonicalIR
from runtime_core.migrate_v1 import canonical_ir_to_state_v2


def test_v1_projection_separates_canonical_state_from_execution_routing():
    ir = CanonicalIR(
        goal="Continue AgentOS",
        project_id="agentmanager",
        capability="agent.reason",
        payload={"instruction": "Continue from current state", "detail": 1},
        constraints=["Do not merge PR #2"],
        context={
            "runtime_policy": {"prefer_push": True, "preferred_target": "provider-bridge"},
            "provider_policy": {"preferred_provider": "academia-gemini-reasoner"},
            "workspace": {"branch": "feature/distributed-agentos-runtime"},
        },
        decisions=[{"decision": "Use project-owned state"}],
        artifacts=[{"kind": "doc", "path": "docs/STATE_KERNEL_V2.md"}],
        pending_tasks=[{"task": "Implement MCP adapter", "priority": 2}],
        continuation={"completed_by": "provider-bridge"},
    )

    projection = canonical_ir_to_state_v2(ir)
    state = projection.state.to_dict()

    assert state["goal"] == "Continue AgentOS"
    assert state["constraints"] == ["Do not merge PR #2"]
    assert len(state["decision_refs"]) == 1
    assert len(state["artifact_refs"]) == 1
    assert len(state["work_items"]) == 2  # pending work + current legacy execution

    # Routing belongs to execution intent, not canonical project state.
    assert "runtime_policy" not in state["metadata"]
    assert "provider_policy" not in state["metadata"]
    assert projection.execution_intent["routing"]["runtime_policy"]["preferred_target"] == "provider-bridge"
    assert projection.execution_intent["routing"]["provider_policy"]["preferred_provider"] == "academia-gemini-reasoner"

    # Decision/artifact bodies are outside the state snapshot and addressed by refs.
    for ref in state["decision_refs"] + state["artifact_refs"]:
        assert ref in projection.records

    assert projection.provenance["source_ir_id"] == ir.ir_id
    assert projection.provenance["source_digest"] == ir.digest()


def test_v1_projection_is_deterministic_for_same_ir():
    ir = CanonicalIR(
        goal="Stable migration",
        project_id="agentmanager",
        capability="agent.reason",
        payload={"instruction": "continue"},
        decisions=[{"decision": "A"}],
        artifacts=[{"path": "a.txt"}],
        pending_tasks=[{"task": "B"}],
    )

    first = canonical_ir_to_state_v2(ir)
    second = canonical_ir_to_state_v2(ir)

    assert first.state.state_id == second.state.state_id
    assert first.records == second.records
    assert first.execution_intent == second.execution_intent

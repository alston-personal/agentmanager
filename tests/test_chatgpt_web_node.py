from agentos_node.chatgpt_web_node import (
    BOOTSTRAP_PROTOCOL,
    build_bootstrap_from_project_state,
)
from runtime_core.canonical_ir import CanonicalIR


def test_bootstrap_compiles_authoritative_project_state_into_web_request():
    ir = CanonicalIR(
        goal="continue 3D layout implementation",
        project_id="layout-3d",
        capability="web.reason",
        payload={"next_action": "inspect existing demo"},
        constraints=["do not redesign from scratch"],
    )
    state = {
        "projectId": "layout-3d",
        "latestTask": {"taskId": "task-123", "status": "succeeded"},
        "currentIR": ir.to_dict(),
        "currentSource": "task_continuation",
        "recommendedAction": "continue",
    }

    packet = build_bootstrap_from_project_state(state)

    assert packet.protocol == BOOTSTRAP_PROTOCOL
    assert packet.runtime_id == "chatgpt-web"
    assert packet.project_id == "layout-3d"
    assert packet.recommended_action == "continue"
    assert packet.latest_task_id == "task-123"
    assert packet.current_ir_id == ir.ir_id
    assert packet.current_ir_digest == ir.digest()
    assert packet.request["input_ir_id"] == ir.ir_id
    assert packet.request["input_digest"] == ir.digest()
    assert packet.request["canonical_ir"]["payload"]["next_action"] == "inspect existing demo"


def test_bootstrap_start_state_has_no_fabricated_ir():
    packet = build_bootstrap_from_project_state(
        {
            "projectId": "new-project",
            "latestTask": None,
            "currentIR": None,
            "currentSource": None,
            "recommendedAction": "start",
        }
    )

    assert packet.recommended_action == "start"
    assert packet.request is None
    assert packet.current_ir_id is None
    assert packet.current_ir_digest is None


def test_bootstrap_rejects_project_mismatch():
    ir = CanonicalIR(goal="g", project_id="project-a", capability="web.reason")
    state = {
        "projectId": "project-b",
        "latestTask": None,
        "currentIR": ir.to_dict(),
        "currentSource": "task_input",
        "recommendedAction": "continue",
    }

    try:
        build_bootstrap_from_project_state(state)
    except ValueError as exc:
        assert "project_id mismatch" in str(exc)
    else:
        raise AssertionError("expected project mismatch to fail closed")

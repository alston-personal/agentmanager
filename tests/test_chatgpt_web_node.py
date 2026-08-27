from agentos_node.chatgpt_web_node import (
    BOOTSTRAP_PROTOCOL,
    build_bootstrap_from_attachment,
)
from runtime_core.canonical_ir import CanonicalIR


def _attachment(project_id, state, *, execution_context=None):
    return {
        "protocol": "agentos.core/v0.1",
        "session_id": "aos_test",
        "project_id": project_id,
        "agent": {"runtime_id": "chatgpt-web"},
        "state": state,
        "execution_context": execution_context or {"compiled": True},
    }


def test_bootstrap_compiles_authoritative_attachment_into_web_request():
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

    packet = build_bootstrap_from_attachment(_attachment("layout-3d", state))

    assert packet.protocol == BOOTSTRAP_PROTOCOL
    assert packet.runtime_id == "chatgpt-web"
    assert packet.project_id == "layout-3d"
    assert packet.session_id == "aos_test"
    assert packet.recommended_action == "continue"
    assert packet.latest_task_id == "task-123"
    assert packet.current_ir_id == ir.ir_id
    assert packet.current_ir_digest == ir.digest()
    assert packet.execution_context == {"compiled": True}
    assert packet.request["input_ir_id"] == ir.ir_id
    assert packet.request["input_digest"] == ir.digest()
    assert packet.request["canonical_ir"]["payload"]["next_action"] == "inspect existing demo"


def test_bootstrap_start_state_has_no_fabricated_ir():
    state = {
        "projectId": "new-project",
        "latestTask": None,
        "currentIR": None,
        "currentSource": None,
        "recommendedAction": "start",
    }
    packet = build_bootstrap_from_attachment(_attachment("new-project", state))

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
        build_bootstrap_from_attachment(_attachment("project-b", state))
    except ValueError as exc:
        assert "project_id mismatch" in str(exc)
    else:
        raise AssertionError("expected project mismatch to fail closed")

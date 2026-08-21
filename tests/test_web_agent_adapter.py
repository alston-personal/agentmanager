import pytest

from agentos_node.web_agent_adapter import REQUEST_PROTOCOL, RESPONSE_PROTOCOL, WebAgentAdapter
from runtime_core.canonical_ir import CanonicalIR


def test_web_agent_adapter_owns_continuation_lineage():
    ir = CanonicalIR(
        goal="handoff between web agents",
        project_id="agentmanager",
        capability="web.reason",
        payload={"question": "next?"},
    )
    adapter = WebAgentAdapter("chatgpt-web")
    request = adapter.build_request(ir)

    assert request["protocol"] == REQUEST_PROTOCOL
    assert request["input_digest"] == ir.digest()
    assert "continuation_ir" not in request["response_contract"]["optional"]
    assert "auto_continue" in request["response_contract"]["reserved_continuation_keys"]

    response = {
        "protocol": RESPONSE_PROTOCOL,
        "runtime_id": "chatgpt-web",
        "input_ir_id": ir.ir_id,
        "input_digest": ir.digest(),
        "status": "succeeded",
        "result": {"decision": "delegate"},
        "next_capability": "web.verify",
        "auto_continue": True,
    }
    result = adapter.consume_response(ir, response)

    assert result.status == "succeeded"
    assert result.continuation_ir is not None
    assert result.continuation_ir.parent_ir_id == ir.ir_id
    assert result.continuation_ir.project_id == ir.project_id
    assert result.continuation_ir.hop_count == ir.hop_count + 1
    assert result.continuation_ir.capability == "web.verify"
    assert result.continuation_ir.continuation["auto_continue"] is True


def test_web_agent_adapter_rejects_tampered_binding():
    ir = CanonicalIR(goal="bind response", project_id="agentmanager", capability="web.reason")
    adapter = WebAgentAdapter("gemini-web")
    response = {
        "protocol": RESPONSE_PROTOCOL,
        "runtime_id": "gemini-web",
        "input_ir_id": ir.ir_id,
        "input_digest": "tampered",
        "status": "succeeded",
        "result": {},
    }
    with pytest.raises(ValueError, match="input_digest"):
        adapter.consume_response(ir, response)


def test_web_agent_adapter_rejects_reserved_continuation_metadata():
    ir = CanonicalIR(goal="protect metadata", project_id="agentmanager", capability="web.reason")
    adapter = WebAgentAdapter("chatgpt-web")
    response = {
        "protocol": RESPONSE_PROTOCOL,
        "runtime_id": "chatgpt-web",
        "input_ir_id": ir.ir_id,
        "input_digest": ir.digest(),
        "status": "succeeded",
        "result": {},
        "auto_continue": False,
        "continuation": {"completed_by": "forged-agent", "auto_continue": True},
    }
    with pytest.raises(ValueError, match="reserved runtime metadata"):
        adapter.consume_response(ir, response)

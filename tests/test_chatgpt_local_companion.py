import json
import threading
from urllib.request import Request, urlopen

from agentos_node.chatgpt_local_companion import (
    ChatGPTLocalCompanionServer,
    ChatGPTLocalCompanionService,
)
from agentos_node.chatgpt_web_node import ChatGPTWebBootstrap


def test_service_returns_compiled_prompt(monkeypatch):
    packet = ChatGPTWebBootstrap(
        protocol="agentos.chatgpt-web-bootstrap/v1",
        runtime_id="chatgpt-web",
        project_id="layout-3d",
        session_id="aos_session",
        recommended_action="continue",
        current_source="task_continuation",
        latest_task_id="task-1",
        current_ir_id="ir-1",
        current_ir_digest="digest-1",
        execution_context={"workspace": {"component": "layoutlib"}},
        request={"canonical_ir": {"goal": "continue 3D Layout"}},
    )

    monkeypatch.setattr(
        "agentos_node.chatgpt_local_companion.bootstrap_chatgpt_web",
        lambda client, project_id, runtime_id: packet,
    )

    service = ChatGPTLocalCompanionService(object())
    result = service.resume("layout-3d", "繼續")

    assert result["project_id"] == "layout-3d"
    assert result["current_ir_digest"] == "digest-1"
    payload = json.loads(result["compiled_prompt"])
    assert payload["execution_context"]["workspace"]["component"] == "layoutlib"
    assert payload["user_intent"] == "繼續"


def test_server_requires_origin_and_transport_token(monkeypatch):
    packet = ChatGPTWebBootstrap(
        protocol="agentos.chatgpt-web-bootstrap/v1",
        runtime_id="chatgpt-web",
        project_id="layout-3d",
        session_id="aos_session",
        recommended_action="continue",
        current_source="task_continuation",
        latest_task_id=None,
        current_ir_id="ir-1",
        current_ir_digest="digest-1",
        execution_context={},
        request={"canonical_ir": {"goal": "continue"}},
    )
    monkeypatch.setattr(
        "agentos_node.chatgpt_local_companion.bootstrap_chatgpt_web",
        lambda client, project_id, runtime_id: packet,
    )

    server = ChatGPTLocalCompanionServer(
        ("127.0.0.1", 0),
        ChatGPTLocalCompanionService(object()),
        token="x" * 24,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        raw = json.dumps({"project_id": "layout-3d", "user_intent": "continue"}).encode()
        req = Request(
            f"http://{host}:{port}/v1/resume",
            data=raw,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://chatgpt.com",
                "X-AgentOS-Companion-Token": "x" * 24,
            },
            method="POST",
        )
        with urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode())
        assert payload["project_id"] == "layout-3d"
        assert payload["current_ir_digest"] == "digest-1"
    finally:
        server.shutdown()
        server.server_close()

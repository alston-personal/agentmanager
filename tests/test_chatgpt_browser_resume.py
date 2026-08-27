import json

from agentos_node.ai_browser_bridge import AiBrowserBridgeClient
from agentos_node.chatgpt_browser_resume import compile_resume_prompt, resume_via_browser
from agentos_node.chatgpt_web_node import ChatGPTWebBootstrap


def _packet():
    return ChatGPTWebBootstrap(
        protocol="agentos.chatgpt-web-bootstrap/v1",
        runtime_id="chatgpt-web",
        project_id="layout-3d",
        session_id="aos_session",
        recommended_action="continue",
        current_source="task_continuation",
        latest_task_id="task-1",
        current_ir_id="ir-1",
        current_ir_digest="digest-1",
        execution_context={"workspace": {"component": "layoutlib", "demo": "https://demo.example"}},
        request={"canonical_ir": {"goal": "continue 3D Layout"}},
    )


def test_compile_resume_prompt_contains_authoritative_continuity_state():
    payload = json.loads(compile_resume_prompt(_packet(), user_intent="繼續3D Layout"))

    assert payload["project_id"] == "layout-3d"
    assert payload["current_ir_id"] == "ir-1"
    assert payload["current_ir_digest"] == "digest-1"
    assert payload["execution_context"]["workspace"]["component"] == "layoutlib"
    assert payload["user_intent"] == "繼續3D Layout"
    assert "Do not redesign" in payload["instruction"]


def test_resume_via_browser_attaches_then_sends_compiled_prompt(monkeypatch):
    packet = _packet()

    class FakeControlPlane:
        pass

    captured = {}

    def fake_bootstrap(control_plane, project_id, *, runtime_id):
        assert project_id == "layout-3d"
        assert runtime_id == "chatgpt-web"
        return packet

    monkeypatch.setattr(
        "agentos_node.chatgpt_browser_resume.bootstrap_chatgpt_web",
        fake_bootstrap,
    )

    def runner(command, timeout):
        captured["command"] = list(command)
        captured["timeout"] = timeout
        return json.dumps({"chatgpt": {"ok": True, "reply": "continued", "elapsedMs": 10}})

    bridge = AiBrowserBridgeClient(runner=runner)
    result = resume_via_browser(
        FakeControlPlane(),
        bridge,
        "layout-3d",
        user_intent="continue",
    )

    assert result.bridge_reply.ok is True
    assert result.bridge_reply.reply == "continued"
    assert captured["command"][:5] == ["bridge", "ask", "--provider", "chatgpt", "--json"]
    prompt = json.loads(captured["command"][5])
    assert prompt["current_ir_digest"] == "digest-1"
    assert prompt["execution_context"]["workspace"]["component"] == "layoutlib"

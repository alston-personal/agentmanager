import json
import threading
from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService
from agentos_node.provider_bridge import (
    AgentProviderBridge,
    GeminiGenerateContentProvider,
    OpenAIResponsesProvider,
    ProviderAdapter,
    ProviderRegistry,
)
from runtime_core.canonical_ir import CanonicalIR


class FakeProvider(ProviderAdapter):
    def __init__(self, provider_id: str, semantic: dict):
        self.provider_id = provider_id
        self.semantic = semantic
        self.calls = []

    def invoke(self, request_envelope: dict):
        self.calls.append(request_envelope)
        return dict(self.semantic)


class FakeHTTPResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_registry_prefers_requested_provider():
    registry = ProviderRegistry()
    first = FakeProvider("provider-a", {"status": "succeeded", "result": {}})
    second = FakeProvider("provider-b", {"status": "succeeded", "result": {}})
    registry.register(first, ["ai.reason"], priority=10)
    registry.register(second, ["ai.reason"], priority=20)

    default_ir = CanonicalIR(goal="route", project_id="agentmanager", capability="ai.reason")
    assert registry.resolve(default_ir) is first

    preferred_ir = CanonicalIR(
        goal="route",
        project_id="agentmanager",
        capability="ai.reason",
        context={"provider_policy": {"preferred_provider": "provider-b"}},
    )
    assert registry.resolve(preferred_ir) is second


def test_provider_bridge_exact_lease_execute_complete_and_continue(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "provider.sqlite3")
    server = DistributedGatewayServer(
        ("127.0.0.1", 0),
        DistributedGatewayService(store),
        token="cp-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        control_plane_url = f"http://{host}:{port}"
        ir = CanonicalIR(
            goal="cross provider continuation",
            project_id="agentmanager",
            capability="ai.reason",
            payload={"question": "verify this"},
        )
        task = store.submit_ir(ir, target_node_id="provider-bridge")

        provider = FakeProvider(
            "openai-test",
            {
                "status": "succeeded",
                "result": {"answer": "draft"},
                "next_capability": "ai.verify",
                "auto_continue": True,
                "continuation": {"note": "handoff"},
            },
        )
        registry = ProviderRegistry()
        registry.register(provider, ["ai.reason"])
        bridge = AgentProviderBridge(
            "provider-bridge",
            registry,
            control_plane_url=control_plane_url,
            control_plane_token="cp-token",
            allow_insecure_control_plane=True,
        )
        envelope = {
            "protocol": "agentos.runtime-dispatch/v1",
            "dispatch_id": "dispatch_test",
            "task_id": task["taskId"],
            "runtime_id": "provider-bridge",
            "capability": ir.capability,
            "project_id": ir.project_id,
            "input_digest": ir.digest(),
            "canonical_ir": ir.to_dict(),
            "control_plane_url": control_plane_url,
        }

        result = bridge.process_dispatch(envelope)
        assert result["status"] == "succeeded"
        assert result["provider_id"] == "openai-test"
        assert len(provider.calls) == 1

        completed = store.get_task(task["taskId"])
        assert completed["status"] == "succeeded"
        continuation = store.load_continuation_ir(task["taskId"])
        assert continuation is not None
        assert continuation.parent_ir_id == ir.ir_id
        assert continuation.capability == "ai.verify"
        assert continuation.continuation["provider_id"] == "openai-test"
        assert result["completed"]["enqueuedTask"]["capability"] == "ai.verify"

        duplicate = bridge.process_dispatch(envelope)
        assert duplicate["status"] == "duplicate_or_claimed"
        assert len(provider.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_openai_responses_adapter_extracts_semantic_json():
    semantic = {"status": "succeeded", "result": {"answer": 42}, "auto_continue": False}
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"output_text": json.dumps(semantic)})

    provider = OpenAIResponsesProvider(
        "openai",
        model="gpt-test",
        api_key="secret",
        opener=opener,
    )
    result = provider.invoke({"canonical_ir": {"goal": "test"}})
    assert result["result"]["answer"] == 42
    assert seen["url"].endswith("/v1/responses")
    assert seen["body"]["model"] == "gpt-test"


def test_gemini_adapter_uses_json_mode_and_extracts_text():
    semantic = {"status": "succeeded", "result": {"verified": True}, "auto_continue": False}
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(semantic)}]}}]}
        )

    provider = GeminiGenerateContentProvider(
        "gemini",
        model="gemini-test",
        api_key="secret",
        opener=opener,
    )
    result = provider.invoke({"canonical_ir": {"goal": "verify"}})
    assert result["result"]["verified"] is True
    assert seen["url"].endswith("/models/gemini-test:generateContent")
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"

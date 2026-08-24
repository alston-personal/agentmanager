import json

from agentos_node.provider_bridge import OpenAIResponsesProvider, PROVIDER_USER_AGENT


class FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_http_provider_sets_agentos_user_agent():
    semantic = {"status": "succeeded", "result": {"ok": True}, "auto_continue": False}
    seen = {}

    def opener(request, timeout):
        seen["user_agent"] = request.get_header("User-agent")
        return FakeHTTPResponse({"output_text": json.dumps(semantic)})

    provider = OpenAIResponsesProvider(
        "test-provider",
        model="test-model",
        api_key="test-key",
        opener=opener,
    )
    result = provider.invoke({"canonical_ir": {"goal": "test"}})

    assert result["result"]["ok"] is True
    assert seen["user_agent"] == PROVIDER_USER_AGENT

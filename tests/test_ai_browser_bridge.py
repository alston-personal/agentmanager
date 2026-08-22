import json

from agentos_node.ai_browser_bridge import AiBrowserBridgeClient


def test_ask_uses_argument_vector_and_normalizes_multi_provider_result():
    seen = {}

    def runner(command, timeout):
        seen["command"] = list(command)
        seen["timeout"] = timeout
        return json.dumps(
            {
                "chatgpt": {"ok": True, "reply": "answer a", "elapsedMs": 10},
                "gemini": {"ok": False, "error": "not signed in", "elapsedMs": 20},
            }
        )

    client = AiBrowserBridgeClient(runner=runner)
    replies = client.ask(
        "continue this project; $(rm -rf /) is text, not shell",
        providers=("chatgpt", "gemini"),
        timeout_seconds=30,
    )
    assert seen["command"][:4] == ["bridge", "ask", "--provider", "chatgpt,gemini"]
    assert seen["command"][-1] == "continue this project; $(rm -rf /) is text, not shell"
    assert seen["timeout"] == 30
    assert replies[0].provider == "chatgpt"
    assert replies[0].ok is True
    assert replies[0].reply == "answer a"
    assert replies[1].provider == "gemini"
    assert replies[1].ok is False
    assert replies[1].error == "not signed in"


def test_ask_accepts_single_provider_result_shape():
    def runner(command, timeout):
        return json.dumps({"ok": True, "reply": "one", "elapsedMs": 5})

    result = AiBrowserBridgeClient(runner=runner).ask("hello", providers=("chatgpt",))
    assert len(result) == 1
    assert result[0].ok is True
    assert result[0].reply == "one"


def test_missing_provider_is_explicit_partial_failure():
    def runner(command, timeout):
        return json.dumps({"chatgpt": {"ok": True, "reply": "ok"}})

    result = AiBrowserBridgeClient(runner=runner).ask(
        "hello", providers=("chatgpt", "gemini")
    )
    assert result[0].ok is True
    assert result[1].ok is False
    assert "missing" in result[1].error


def test_search_conversations_normalizes_provider_keyed_results():
    seen = {}

    def runner(command, timeout):
        seen["command"] = list(command)
        return json.dumps(
            {
                "chatgpt": {
                    "results": [
                        {
                            "id": "conv-1",
                            "title": "AgentOS state kernel",
                            "url": "https://chatgpt.com/c/conv-1",
                        }
                    ]
                },
                "gemini": [
                    {
                        "conversationId": "g-1",
                        "title": "AgentOS review",
                        "url": "https://gemini.google.com/app/g-1",
                    }
                ],
            }
        )

    matches = AiBrowserBridgeClient(runner=runner).search_conversations(
        "AgentOS", providers=("chatgpt", "gemini"), limit=5
    )
    assert seen["command"] == [
        "bridge",
        "chat",
        "search",
        "AgentOS",
        "--provider",
        "chatgpt,gemini",
        "--limit",
        "5",
        "--json",
    ]
    assert {item.provider for item in matches} == {"chatgpt", "gemini"}
    assert {item.conversation_id for item in matches} == {"conv-1", "g-1"}


def test_invalid_inputs_fail_before_external_bridge_call():
    calls = []

    def runner(command, timeout):
        calls.append(command)
        return "{}"

    client = AiBrowserBridgeClient(runner=runner)
    for operation in (
        lambda: client.ask(""),
        lambda: client.ask("x", providers=()),
        lambda: client.search_conversations(""),
        lambda: client.search_conversations("x", limit=0),
    ):
        try:
            operation()
        except ValueError:
            pass
        else:
            raise AssertionError("expected validation failure")
    assert calls == []

import json

import pytest

from agentos_node.gemini_web_worker import (
    GeminiWebError,
    GeminiWebRelay,
    parse_semantic_response,
)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def ask(self, prompt, *, timeout_seconds=180.0):
        self.prompts.append(prompt)
        return self.response


def test_parse_semantic_response_accepts_plain_json():
    value = parse_semantic_response(
        json.dumps({"status": "succeeded", "result": {"answer": "ok"}})
    )
    assert value["status"] == "succeeded"
    assert value["result"]["answer"] == "ok"


def test_parse_semantic_response_accepts_fenced_json():
    value = parse_semantic_response(
        "```json\n{\"status\":\"succeeded\",\"result\":{\"answer\":\"ok\"}}\n```"
    )
    assert value["result"] == {"answer": "ok"}


def test_parse_semantic_response_rejects_non_agentos_shape():
    with pytest.raises(GeminiWebError):
        parse_semantic_response('{"hello":"world"}')


def test_relay_requires_protocol_provider_and_instruction():
    session = FakeSession('{"status":"succeeded","result":{"answer":"ok"}}')
    relay = GeminiWebRelay(session, provider_id="gemini-web-shadow")

    with pytest.raises(GeminiWebError):
        relay.invoke({})
    with pytest.raises(GeminiWebError):
        relay.invoke({"protocol": "agentos.provider-request/v1", "provider_id": "other", "instruction": "x"})
    with pytest.raises(GeminiWebError):
        relay.invoke({"protocol": "agentos.provider-request/v1", "provider_id": "gemini-web-shadow"})


def test_relay_returns_semantic_response_only():
    session = FakeSession('{"status":"succeeded","result":{"answer":"gemini"},"auto_continue":false}')
    relay = GeminiWebRelay(session, provider_id="gemini-web-shadow")
    result = relay.invoke(
        {
            "protocol": "agentos.provider-request/v1",
            "provider_id": "gemini-web-shadow",
            "request": {"project_id": "p"},
            "instruction": "return AgentOS JSON",
        }
    )
    assert session.prompts == ["return AgentOS JSON"]
    assert result == {
        "semantic_response": {
            "status": "succeeded",
            "result": {"answer": "gemini"},
            "auto_continue": False,
        }
    }

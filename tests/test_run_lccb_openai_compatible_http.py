import json

from scripts.run_lccb_openai_compatible import _chat


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": '{"ok":"ok"}'}}]}).encode()


def test_chat_uses_canonical_accept_and_user_agent(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("scripts.run_lccb_openai_compatible.urllib.request.urlopen", fake_urlopen)

    content = _chat(
        "https://example.test/v1",
        "secret",
        "model",
        [{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=64,
    )

    assert content == '{"ok":"ok"}'
    headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert headers["accept"] == "application/json"
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Bearer secret"
    assert "AgentOS/1.0" in headers["user-agent"]
    assert captured["timeout"] == 180

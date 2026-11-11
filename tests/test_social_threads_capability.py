from __future__ import annotations

import json

from agentos_node.social.contracts import SocialRequest, social_request_digest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.governance import RuntimeWriteAcceptance
from agentos_node.social.public_threads import ThreadsPublicReadError, normalize_url, parse_public_post_html, resolve_input_url, resolve_public_post
from agentos_node.social.provider import SocialProvider
from agentos_node.social.threads import ThreadsCapability, ThreadsProviderConfig


class FakeTransport:
    def __init__(self):
        self.calls = []

    def config(self):
        return ThreadsProviderConfig("app-id", "server-only-secret", "https://core.example/callback")

    def authorization_url(self, state, *, auth_profile='persona'):
        return f"https://threads.net/oauth/authorize?client_id=app-id&state={state}"

    def exchange_code(self, code):
        assert code == "provider-code"
        return "SERVER-ONLY-TOKEN"

    def identity(self, token):
        assert token == "SERVER-ONLY-TOKEN"
        return {"id": "42", "username": "milkcat"}

    def api(self, path, *, token, method="GET", params=None):
        assert token == "SERVER-ONLY-TOKEN"
        self.calls.append((path, method, dict(params or {})))
        return {"id": "published-99"}

    def revoke(self, token):
        assert token == "SERVER-ONLY-TOKEN"


def test_public_threads_reader_is_strict_and_bounded_contract():
    assert normalize_url("https://threads.com/@cat/post/ABC?x=secret") == "https://www.threads.com/@cat/post/ABC"
    html = '<meta property="og:description" content="hello world">'
    source = parse_public_post_html(html, "https://www.threads.com/@cat/post/ABC")
    assert source["username"] == "cat"
    assert source["text"] == "hello world"
    try:
        normalize_url("http://evil.example/@cat/post/ABC")
    except ThreadsPublicReadError as exc:
        assert str(exc) == "invalid_threads_url"
    else:
        raise AssertionError("untrusted host should fail")


def test_leopardcat_teacher_text_attachment_uses_same_generic_request_contract():
    vault = EphemeralCredentialVault()
    vault.bind(AccountBinding("leopardcat-tarot:threads:42", "leopardcat-tarot", "threads", "42", "milkcat"), "SERVER-ONLY-TOKEN")
    transport = FakeTransport()
    capability = ThreadsCapability(vault, transport)
    request = SocialRequest(
        product_id="leopardcat-tarot", platform="threads", operation="publish",
        account_binding_id="leopardcat-tarot:threads:42", target_account_id="42",
        primary_text="<=500-char intent",
        text_attachment={"plaintext": "full Master interpretation", "link_attachment_url": "https://example.test/share/1"},
        write_intent_id="user-confirmation-1",
    )
    acceptance = RuntimeWriteAcceptance(
        "runtime-accept-1", "leopardcat-tarot", "threads",
        frozenset({"publish"}), frozenset({request.account_binding_id}),
        social_request_digest(request),
    )
    receipt = capability.publish(request, acceptance=acceptance)
    assert receipt["ok"] is True
    assert "SERVER-ONLY-TOKEN" not in str(receipt)
    attachment = json.loads(transport.calls[0][2]["text_attachment"])
    assert attachment["plaintext"] == "full Master interpretation"
    assert transport.calls[0][2]["auto_publish_text"] == "true"
    assert transport.calls[0][0] == "me/threads"


def test_leopardcat_and_vendor_use_same_generic_provider_for_read_contract():
    def resolver(url):
        return {"type": "threads", "author": "@cat", "username": "cat", "text": "source", "url": normalize_url(url)}
    provider = SocialProvider(public_threads_resolver=resolver)
    for product_id in ("leopardcat-tarot", "vendor-reputation-service"):
        receipt = provider.invoke({"product_id": product_id, "platform": "threads", "operation": "public_post.read", "object_id": "https://threads.com/@cat/post/ABC"})
        assert receipt["ok"] is True
        assert receipt["product_id"] == product_id
        assert receipt["capability"] == "social.threads.public_post.read"
        assert receipt["result"]["source"]["text"] == "source"


def test_connect_exposes_no_provider_secret_or_token():
    vault = EphemeralCredentialVault()
    capability = ThreadsCapability(vault, FakeTransport())
    request = SocialRequest(product_id="leopardcat-tarot", platform="threads", operation="connect", return_to="/reading/1")
    redirect = capability.begin_connect(request, browser_session_id="browser-session")
    assert "server-only-secret" not in str(redirect)
    completed = capability.complete_connect(product_id="leopardcat-tarot", browser_session_id="browser-session", state=redirect["state"], code="provider-code")
    assert completed["connected"] is True
    assert "SERVER-ONLY-TOKEN" not in str(completed)
    assert "provider-code" not in str(completed)
    assert completed["return_to"] == "/reading/1"


def test_core_share_resolver_is_used_by_shared_social_provider(monkeypatch):
    import urllib.request

    calls = []

    class Response:
        headers = type("Headers", (), {"get_content_charset": lambda self: "utf-8"})()
        def __init__(self, final, content):
            self.final = final
            self.content = content
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def geturl(self): return self.final
        def read(self, amount): return self.content[:amount]

    class Opener:
        def open(self, req, timeout):
            calls.append(("share", req.full_url))
            return Response("https://www.threads.com/@cat/post/ABC?igsh=1", b"x")

    def fake_urlopen(request, timeout):
        calls.append(("post", request.full_url))
        return Response("https://www.threads.com/@cat/post/ABC",
                        b'<meta property="og:description" content="read from share">')

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = SocialProvider()
    receipt = provider.invoke({
        "product_id": "hermes", "platform": "threads",
        "operation": "public_post.read",
        "object_id": "https://www.threads.com/share/BAaVMSEntH",
    })
    assert receipt["ok"] is True
    source = receipt["result"]["source"]
    assert source["url"] == "https://www.threads.com/@cat/post/ABC"
    assert source["text"] == "read from share"
    assert calls == [
        ("share", "https://www.threads.com/share/BAaVMSEntH"),
        ("post", "https://www.threads.com/@cat/post/ABC"),
    ]


def test_core_share_resolver_rejects_redirect_outside_threads(monkeypatch):
    import pytest
    import urllib.request

    def fake_opener(*handlers):
        handler = handlers[0]

        class Opener:
            def open(self, request, timeout):
                handler.redirect_request(request, None, 302, "redirect", {},
                                         "https://evil.example/@cat/post/ABC")
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_opener)
    with pytest.raises(ThreadsPublicReadError, match="unsafe_threads_redirect"):
        resolve_input_url("https://threads.com/share/BAaVMSEntH")


def test_core_share_resolver_rejects_untrusted_urls():
    import pytest
    for value in ("http://threads.com/share/BAaVMSEntH", "https://evil.example/share/BAaVMSEntH",
                  "https://threads.com/share/../post/ABC", "https://threads.com/@cat",
                  "https://user:password@threads.com/share/BAaVMSEntH"):
        with pytest.raises(ThreadsPublicReadError, match="invalid_threads_url"):
            resolve_input_url(value)

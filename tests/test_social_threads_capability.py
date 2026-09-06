from __future__ import annotations

from agentos_node.social.contracts import SocialRequest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.governance import RuntimeWriteAcceptance
from agentos_node.social.public_threads import ThreadsPublicReadError, normalize_url, parse_public_post_html
from agentos_node.social.provider import SocialProvider
from agentos_node.social.threads import ThreadsCapability, ThreadsProviderConfig


class FakeTransport:
    def __init__(self):
        self.calls = []

    def config(self):
        return ThreadsProviderConfig("app-id", "server-only-secret", "https://core.example/callback")

    def authorization_url(self, state):
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
        product_id="leopardcat-tarot",
        platform="threads",
        operation="publish",
        account_binding_id="leopardcat-tarot:threads:42",
        target_account_id="42",
        primary_text="<=500-char intent",
        text_attachment="full Master interpretation",
        write_intent_id="user-confirmation-1",
    )
    acceptance = RuntimeWriteAcceptance("runtime-accept-1", "leopardcat-tarot", "threads", frozenset({"publish"}), frozenset({request.account_binding_id}))
    receipt = capability.publish(request, acceptance=acceptance)
    assert receipt["ok"] is True
    assert "SERVER-ONLY-TOKEN" not in str(receipt)
    assert transport.calls[0][2]["text_attachment"] == "full Master interpretation"
    assert transport.calls[0][2]["auto_publish_text"] == "true"


def test_leopardcat_and_vendor_use_same_generic_provider_for_read_contract():
    def resolver(url):
        return {"type": "threads", "author": "@cat", "username": "cat", "text": "source", "url": normalize_url(url)}

    provider = SocialProvider(public_threads_resolver=resolver)
    for product_id in ("leopardcat-tarot", "vendor-reputation-service"):
        receipt = provider.invoke({
            "product_id": product_id,
            "platform": "threads",
            "operation": "public_post.read",
            "object_id": "https://threads.com/@cat/post/ABC",
        })
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

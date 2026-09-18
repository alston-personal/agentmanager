from agentos_node.social.contracts import SocialRequest
from agentos_node.social.credentials import AccountBinding
from agentos_node.social.threads import THREADS_SCOPES, ThreadsCapability, ThreadsProviderConfig


class FakeVault:
    def __init__(self):
        self.binding = AccountBinding("galaxy:threads:42", "galaxy", "threads", "42", "alice")

    def get_binding(self, binding_id):
        return self.binding if binding_id == self.binding.binding_id else None

    def get_access_token(self, binding_id):
        assert binding_id == self.binding.binding_id
        return "secret-token"


class FakeTransport:
    def config(self):
        return ThreadsProviderConfig("app", "secret", "https://example.test/callback")

    def identity(self, token):
        assert token == "secret-token"
        return {"id": "42", "username": "alice", "name": "Alice", "threads_profile_picture_url": "https://img.test/a.jpg"}

    def paged(self, path, *, token, params, max_pages=3):
        assert token == "secret-token"
        if path == "me/threads":
            return [{"id": "p1", "username": "alice", "text": "root", "timestamp": "2026-09-17T00:00:00+0000", "permalink": "https://www.threads.com/@alice/post/p1", "has_replies": True}]
        if path == "p1/conversation":
            return [
                {"id": "r1", "username": "bob", "text": "hello", "timestamp": "2026-09-17T00:10:00+0000", "is_reply": True, "root_post": {"id": "p1"}, "replied_to": {"id": "p1"}},
                {"id": "r2", "username": "alice", "text": "thanks", "timestamp": "2026-09-17T00:11:00+0000", "is_reply": True, "is_reply_owned_by_me": True, "root_post": {"id": "p1"}, "replied_to": {"id": "r1"}},
            ]
        raise AssertionError(path)


def request(operation, object_id=None, product_id="galaxy"):
    return SocialRequest(
        product_id=product_id,
        platform="threads",
        operation=operation,
        account_binding_id="galaxy:threads:42",
        object_id=object_id,
    )


def test_oauth_requests_reply_read_permission():
    assert "threads_basic" in THREADS_SCOPES
    assert "threads_read_replies" in THREADS_SCOPES


def test_identity_read_is_secret_free():
    cap = ThreadsCapability(FakeVault(), FakeTransport())
    result = cap.status(request("identity.read"))
    assert result["ok"] is True
    assert result["capability"] == "social.threads.identity.read"
    assert result["result"]["identity"]["username"] == "alice"
    assert "secret-token" not in repr(result)


def test_post_and_conversation_reads_are_bounded_provider_data():
    cap = ThreadsCapability(FakeVault(), FakeTransport())
    posts = cap.status(request("post.read"))
    assert posts["ok"] is True
    assert posts["result"]["items"][0]["id"] == "p1"

    replies = cap.status(request("replies.read", "p1"))
    assert replies["ok"] is True
    assert [item["username"] for item in replies["result"]["items"]] == ["bob", "alice"]
    assert replies["result"]["items"][1]["replied_to"] == {"id": "r1"}


def test_read_binding_is_product_scoped():
    cap = ThreadsCapability(FakeVault(), FakeTransport())
    result = cap.status(request("identity.read", product_id="other"))
    assert result["ok"] is False
    assert result["error_code"] == "account_binding_mismatch"


def test_threads_authorization_url_uses_web_host():
    from agentos_node.social.threads import ThreadsProviderTransport
    transport = ThreadsProviderTransport(
        lambda: ThreadsProviderConfig("app", "secret", "https://example.test/callback")
    )
    url = transport.authorization_url("state-1")
    assert url.startswith("https://www.threads.com/oauth/authorize?")
    assert "state=state-1" in url

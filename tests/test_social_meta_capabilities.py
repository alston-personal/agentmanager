from pathlib import Path

from agentos_node.social.credentials import CredentialBinding, EnvironmentCredentialResolver
from agentos_node.social.facebook import FacebookCapability
from agentos_node.social.instagram import InstagramCapability


class Resolver(EnvironmentCredentialResolver):
    def __init__(self, ref, env, platform):
        super().__init__({ref: CredentialBinding(ref, env, platform)})
        self.ref = ref
    def resolve(self, credential_ref):
        assert credential_ref == self.ref
        return "secret-not-for-receipt"
    def present(self, credential_ref):
        return True


class Resp:
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class FakeRequests:
    def __init__(self, gets=None, posts=None):
        self.gets = list(gets or [])
        self.posts = list(posts or [])
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Resp(self.gets.pop(0))
    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Resp(self.posts.pop(0))


def test_facebook_identity_and_secret_free_receipt():
    fake = FakeRequests(gets=[{"id": "page1", "name": "Demo Page"}])
    cap = FacebookCapability("facebook/test", Resolver("facebook/test", "FB", "facebook"), page_id="page1")
    cap._requests = lambda: fake
    receipt = cap.identity_read().to_dict()
    assert receipt["ok"] is True
    assert receipt["platform_object_id"] == "page1"
    assert "secret-not-for-receipt" not in str(receipt)


def test_facebook_publish_photo(tmp_path: Path):
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"fake")
    fake = FakeRequests(gets=[{"id": "page1", "name": "Demo"}], posts=[{"id": "photo1", "post_id": "page1_post1"}])
    cap = FacebookCapability("facebook/test", Resolver("facebook/test", "FB", "facebook"), page_id="page1")
    cap._requests = lambda: fake
    receipt = cap.publish_photo("Title", "Summary", str(image)).to_dict()
    assert receipt["ok"] is True
    assert receipt["platform_object_id"] == "page1_post1"
    assert receipt["capability"] == "social.facebook.publish"


def test_instagram_publish_and_reply():
    fake = FakeRequests(
        gets=[{"id": "ig1", "username": "demo"}, {"permalink": "https://instagram.example/p/x"}],
        posts=[{"id": "container1"}, {"id": "media1"}, {"id": "comment1"}],
    )
    cap = InstagramCapability("instagram/test", Resolver("instagram/test", "IG", "instagram"), ig_id="ig1", publish_wait_seconds=0)
    cap._requests = lambda: fake
    identity = cap.identity_read().to_dict()
    assert identity["ok"] is True
    published = cap.publish_image("Title", "Summary", "https://example.com/a.jpg").to_dict()
    assert published["ok"] is True
    assert published["platform_object_id"] == "media1"
    reply = cap.comment("media1", "hello").to_dict()
    assert reply["ok"] is True
    assert reply["capability"] == "social.instagram.reply"
    assert "secret-not-for-receipt" not in str((identity, published, reply))

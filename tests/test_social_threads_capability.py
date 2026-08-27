from agentos_node.social.credentials import CredentialBinding, EnvironmentCredentialResolver
from agentos_node.social.threads import ThreadsCapability, ThreadsAPIError


class FakeResolver(EnvironmentCredentialResolver):
    def __init__(self):
        super().__init__({
            "threads/test": CredentialBinding("threads/test", "TEST_THREADS_TOKEN", "threads")
        })

    def resolve(self, credential_ref: str) -> str:
        assert credential_ref == "threads/test"
        return "secret-never-in-receipt"

    def present(self, credential_ref: str) -> bool:
        return True


class FakeThreads(ThreadsCapability):
    def __init__(self, responses):
        super().__init__("threads/test", resolver=FakeResolver(), publish_wait_seconds=0)
        self.responses = list(responses)
        self.calls = []

    def _request(self, method, path, params=None):
        self.calls.append((method, path, params or {}))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_identity_receipt_never_contains_token():
    cap = FakeThreads([{"id": "u1", "username": "demo"}])
    receipt = cap.identity_read().to_dict()
    assert receipt["ok"] is True
    assert receipt["capability"] == "social.threads.identity.read"
    assert receipt["result"]["username"] == "demo"
    assert "secret-never-in-receipt" not in str(receipt)


def test_replies_read_returns_normalized_evidence():
    cap = FakeThreads([{"data": [{"id": "r1", "text": "推薦 A", "username": "x"}], "paging": {}}])
    receipt = cap.replies_read("thread-1").to_dict()
    assert receipt["ok"] is True
    assert receipt["result"]["count"] == 1
    assert receipt["result"]["replies"][0]["id"] == "r1"


def test_api_denial_is_a_failed_receipt_not_an_exception():
    cap = FakeThreads([ThreadsAPIError("10", "permission denied")])
    receipt = cap.post_read("third-party-thread").to_dict()
    assert receipt["ok"] is False
    assert receipt["error_code"] == "10"
    assert "permission denied" in receipt["error_message"]


def test_publish_uses_two_stage_api_and_returns_receipt():
    cap = FakeThreads([
        {"id": "u1"},
        {"id": "container-1"},
        {"id": "thread-1"},
        {"permalink": "https://www.threads.com/@demo/post/x"},
    ])
    receipt = cap.publish("hello").to_dict()
    assert receipt["ok"] is True
    assert receipt["capability"] == "social.threads.publish"
    assert receipt["platform_object_id"] == "thread-1"
    assert cap.calls[1][1] == "u1/threads"
    assert cap.calls[2][1] == "u1/threads_publish"

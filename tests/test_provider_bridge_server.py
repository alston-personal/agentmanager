import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agentos_node.provider_bridge_server import ProviderBridgeServer


class FakeRegistry:
    def describe(self):
        return [{"providerId": "fake"}]


class FakeBridge:
    runtime_id = "provider-bridge"
    registry = FakeRegistry()

    def __init__(self):
        self.seen = []
        self.event = threading.Event()

    def process_dispatch(self, envelope):
        self.seen.append(envelope)
        self.event.set()
        return {"status": "succeeded", "task_id": envelope["task_id"]}


def _post(url: str, body: dict, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_provider_bridge_server_accepts_wake_asynchronously():
    bridge = FakeBridge()
    server = ProviderBridgeServer(("127.0.0.1", 0), bridge, token="bridge-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        status, payload = _post(
            f"http://{host}:{port}/v1/runtime-dispatch",
            {"dispatch_id": "dispatch-1", "task_id": "task-1"},
            token="bridge-token",
        )
        assert status == 202
        assert payload["status"] == "accepted"
        assert payload["external_ref"].endswith(":dispatch-1")
        assert bridge.event.wait(2)
        assert bridge.seen[0]["task_id"] == "task-1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_provider_bridge_server_rejects_wrong_token():
    bridge = FakeBridge()
    server = ProviderBridgeServer(("127.0.0.1", 0), bridge, token="bridge-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        try:
            _post(
                f"http://{host}:{port}/v1/runtime-dispatch",
                {"dispatch_id": "dispatch-1", "task_id": "task-1"},
                token="wrong-token",
            )
            raise AssertionError("expected HTTP 401")
        except HTTPError as exc:
            assert exc.code == 401
        assert not bridge.event.is_set()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

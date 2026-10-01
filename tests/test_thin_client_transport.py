from __future__ import annotations

import json

from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy
from agentos_node.thin_client_transport import ClientConfig, ThinClientTransport


def test_successful_heartbeat_writes_local_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTOS_CLIENT_HOME", str(tmp_path))
    client = ThinClient(NodeIdentity("realm-test", "node-test"), ThinClientPolicy())
    config = ClientConfig(
        one_url="https://agentos.example.invalid",
        realm_id="realm-test",
        node_id="node-test",
        node_token="secret-test-token",
    )
    transport = ThinClientTransport(client, config)

    def fake_request(url, **kwargs):
        assert url.endswith("/v1/heartbeat")
        assert kwargs["token"] == "secret-test-token"
        return {"ok": True}

    monkeypatch.setattr(ThinClientTransport, "_request", staticmethod(fake_request))
    result = transport.heartbeat()

    assert result == {"ok": True}
    lease_path = tmp_path / "heartbeat-lease.json"
    assert lease_path.exists()
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    assert lease["schema"] == "agentos.node-heartbeat-lease/v0.1"
    assert lease["realm_id"] == "realm-test"
    assert lease["node_id"] == "node-test"
    assert lease["recorded_at_unix"] > 0


def test_failed_heartbeat_does_not_advance_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTOS_CLIENT_HOME", str(tmp_path))
    client = ThinClient(NodeIdentity("realm-test", "node-test"), ThinClientPolicy())
    config = ClientConfig(
        one_url="https://agentos.example.invalid",
        realm_id="realm-test",
        node_id="node-test",
        node_token="secret-test-token",
    )
    transport = ThinClientTransport(client, config)

    def fail_request(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ThinClientTransport, "_request", staticmethod(fail_request))

    try:
        transport.heartbeat()
    except RuntimeError as exc:
        assert "network down" in str(exc)
    else:
        raise AssertionError("heartbeat should fail")

    assert not (tmp_path / "heartbeat-lease.json").exists()

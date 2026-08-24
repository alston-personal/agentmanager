import json

from agentos_node.antigravity_relay import AntigravityRelayClient, RELAY_SCHEMA


def test_submit_creates_bounded_capsule(tmp_path):
    client = AntigravityRelayClient(tmp_path / "relay")
    payload = client.submit(
        project_id="agentmanager",
        canonical_ir={"ir_id": "ir-1", "goal": "continue"},
        instruction="Continue current AgentOS goal",
        workspace="/home/ubuntu/agentmanager",
    )
    assert payload["schema"] == RELAY_SCHEMA
    assert payload["authority"]["direct_session_impersonation"] is False
    capsule = client.paths.inbox / f"{payload['capsule_id']}.json"
    assert capsule.exists()
    stored = json.loads(capsule.read_text(encoding="utf-8"))
    assert stored["digest"].startswith("sha256:")


def test_missing_receipt_returns_none(tmp_path):
    client = AntigravityRelayClient(tmp_path / "relay")
    assert client.receipt("relay-does-not-exist") is None

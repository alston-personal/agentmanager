from pathlib import Path

from agent_core.control_plane import ControlPlaneStore


NODE = {
    "apiVersion": "agentos/v1",
    "kind": "Node",
    "metadata": {"id": "node-test-01", "version": "0.1.0"},
    "spec": {
        "capabilities": [{"name": "ai.generate", "versions": ["0.1.0"]}],
    },
}


def test_registration_heartbeat_capability_and_idempotent_task(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "control-plane.sqlite3")

    assert store.register_node(NODE)["status"] == "registered"
    assert store.heartbeat("node-test-01", {"gpu": {"count": 1}})["status"] == "online"
    assert store.find_capable_nodes("ai.generate")[0]["nodeId"] == "node-test-01"

    first = store.submit_task("ai.generate", {"prompt": "test"}, "stable-key")
    second = store.submit_task("ai.generate", {"prompt": "changed"}, "stable-key")
    assert first["taskId"] == second["taskId"]
    assert second["payload"] == {"prompt": "test"}

    leased = store.lease_next_task("node-test-01", ["ai.generate"])
    assert leased["status"] == "leased"
    assert leased["targetNodeId"] == "node-test-01"
    assert store.update_task(leased["taskId"], "succeeded", {"text": "ok"})["status"] == "succeeded"

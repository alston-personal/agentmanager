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


def test_overdue_leases_are_fenced_without_automatic_replay(tmp_path: Path):
    import sqlite3

    db = tmp_path / "control-plane.sqlite3"
    store = ControlPlaneStore(db)
    task = store.submit_task("ai.generate", {"prompt": "effect"}, "lease-expire-key")
    lease = store.lease_next_task("node-test-01", ["ai.generate"], lease_seconds=60)
    assert lease["taskId"] == task["taskId"]

    # Simulate an executor disappearing and its lease crossing the deadline.
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE tasks SET status='running', lease_until='2000-01-01T00:00:00Z' WHERE task_id=?",
            (task["taskId"],),
        )

    # Reopening the store represents a new service process after restart.
    recovered = ControlPlaneStore(db)
    expired = recovered.expire_overdue_leases()
    assert len(expired) == 1
    assert expired[0]["taskId"] == task["taskId"]
    assert expired[0]["status"] == "expired"
    assert expired[0]["result"]["sideEffectState"] == "unknown"
    assert expired[0]["result"]["recoveryRequired"] is True
    assert recovered.expire_overdue_leases() == []
    assert recovered.lease_next_task("node-test-01", ["ai.generate"]) is None
    assert recovered.submit_task("ai.generate", {"prompt": "new"}, "lease-expire-key")["status"] == "expired"


def test_unexpired_lease_not_reconciled(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "control-plane.sqlite3")
    store.submit_task("ai.generate", {}, "fresh-lease")
    assert store.lease_next_task("node-test-01", ["ai.generate"], lease_seconds=3600)
    assert store.expire_overdue_leases() == []

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
    assert store.complete_leased_task(leased["taskId"], "node-test-01", leased["leaseUntil"], "succeeded", {"text": "ok"})["status"] == "succeeded"


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


def test_late_worker_receipt_cannot_override_expired_task(tmp_path: Path):
    import sqlite3
    import pytest

    db = tmp_path / "control-plane.sqlite3"
    store = ControlPlaneStore(db)
    task = store.submit_task("ai.generate", {}, "stale-ack")
    lease = store.lease_next_task("node-test-01", ["ai.generate"])
    assert lease is not None
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00Z' WHERE task_id=?",
            (task["taskId"],),
        )
    assert store.expire_overdue_leases()[0]["status"] == "expired"
    with pytest.raises(ValueError, match="stale or unauthorized"):
        store.complete_leased_task(
            task["taskId"], "node-test-01", lease["leaseUntil"], "succeeded",
            {"effect": "possibly happened"},
        )
    assert store.submit_task("ai.generate", {}, "stale-ack")["status"] == "expired"


def test_current_worker_receipt_accepted_once_only(tmp_path: Path):
    import pytest

    store = ControlPlaneStore(tmp_path / "control-plane.sqlite3")
    task = store.submit_task("ai.generate", {}, "fresh-ack")
    lease = store.lease_next_task("node-test-01", ["ai.generate"])
    assert lease is not None
    with pytest.raises(ValueError, match="stale or unauthorized"):
        store.complete_leased_task(task["taskId"], "other-node", lease["leaseUntil"], "succeeded")
    done = store.complete_leased_task(
        task["taskId"], "node-test-01", lease["leaseUntil"], "succeeded", {"ok": True}
    )
    assert done["status"] == "succeeded"
    assert done["result"] == {"ok": True}
    with pytest.raises(ValueError, match="stale or unauthorized"):
        store.complete_leased_task(task["taskId"], "node-test-01", lease["leaseUntil"], "failed")


def test_legacy_update_cannot_overwrite_worker_receipt_or_expired_state(tmp_path: Path):
    import pytest
    store = ControlPlaneStore(tmp_path / "control-plane.sqlite3")
    pending = store.submit_task("ai.generate", {}, "administrative-cancel")
    assert store.update_task(pending["taskId"], "cancelled")["status"] == "cancelled"
    with pytest.raises(ValueError, match="only supports"):
        store.update_task(pending["taskId"], "succeeded")

    store.submit_task("ai.generate", {}, "active-worker")
    lease = store.lease_next_task("node-test-01", ["ai.generate"])
    assert lease is not None
    with pytest.raises(ValueError, match="not submitted"):
        store.update_task(lease["taskId"], "cancelled")
    with pytest.raises(ValueError, match="only supports"):
        store.update_task(lease["taskId"], "succeeded", {"fake": True})
    assert store.complete_leased_task(
        lease["taskId"], "node-test-01", lease["leaseUntil"], "succeeded"
    )["status"] == "succeeded"


def test_supervisor_lease_reconcile_adapter_never_replays_side_effects(tmp_path: Path):
    from scripts.control_plane_lease_reconcile import reconcile
    import sqlite3

    db = tmp_path / "control-plane.sqlite3"
    store = ControlPlaneStore(db)
    task = store.submit_task("ai.generate", {"prompt": "effect"}, "reconcile-once")
    lease = store.lease_next_task("node-test-01", ["ai.generate"])
    assert lease is not None
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00Z' WHERE task_id=?",
            (task["taskId"],),
        )
    first = reconcile(db)
    assert first["expired_count"] == 1
    assert first["tasks"][0]["side_effect_state"] == "unknown"
    assert first["tasks"][0]["recovery_required"] is True
    assert first["auto_replayed"] is False
    second = reconcile(db)
    assert second["expired_count"] == 0
    assert second["auto_replayed"] is False

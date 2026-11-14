from pathlib import Path

import pytest

from agent_core.distributed_control_plane import DistributedControlPlane
from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import ExecutionOutcome, RemoteRuntimeWorker


def test_ir_task_lease_result_and_auto_continuation(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    ir = CanonicalIR(
        goal="continue distributed workflow",
        project_id="agentmanager",
        capability="step.one",
        payload={"value": 1},
    )

    first = store.submit_ir(ir)
    duplicate = store.submit_ir(ir)
    assert duplicate["taskId"] == first["taskId"]

    lease = store.lease_next_ir("worker-a", ["step.one"])
    assert lease is not None
    assert lease.ir.ir_id == ir.ir_id
    assert lease.ir.digest() == ir.digest()

    worker = RemoteRuntimeWorker("worker-a")
    worker.register(
        "step.one",
        lambda current: ExecutionOutcome(
            result={"value": current.payload["value"] + 1},
            next_capability="step.two",
            auto_continue=True,
        ),
    )
    runtime_result = worker.execute(lease.ir)
    completed = store.complete_ir(lease.task_id, runtime_result, lease_epoch=lease.lease_epoch)

    assert completed["task"]["status"] == "succeeded"
    assert completed["continuationBlocked"] is None
    assert completed["enqueuedTask"] is not None
    assert completed["enqueuedTask"]["capability"] == "step.two"

    continuation = store.load_continuation_ir(lease.task_id)
    assert continuation is not None
    assert continuation.parent_ir_id == ir.ir_id
    assert continuation.hop_count == 1
    assert continuation.payload == {"value": 2}

    second_lease = store.lease_next_ir("worker-b", ["step.two"])
    assert second_lease is not None
    assert second_lease.ir.ir_id == continuation.ir_id


def test_runtime_result_must_match_leased_ir(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    ir = CanonicalIR(goal="verify result binding", project_id="agentmanager", capability="safe.step")
    store.submit_ir(ir)
    lease = store.lease_next_ir("worker-a", ["safe.step"])
    assert lease is not None

    worker = RemoteRuntimeWorker("worker-a")
    worker.register("safe.step", lambda current: {"ok": True})
    result = worker.execute(lease.ir)
    result.input_digest = "tampered"

    with pytest.raises(ValueError, match="input_digest"):
        store.complete_ir(lease.task_id, result, lease_epoch=lease.lease_epoch)

    assert store.get_task(lease.task_id)["status"] == "leased"


def test_auto_continuation_has_hop_limit(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3", max_auto_continuation_hops=2)
    ir = CanonicalIR(
        goal="guard loops",
        project_id="agentmanager",
        capability="loop.step",
        hop_count=2,
    )
    store.submit_ir(ir)
    lease = store.lease_next_ir("worker-a", ["loop.step"])
    assert lease is not None

    worker = RemoteRuntimeWorker("worker-a")
    worker.register(
        "loop.step",
        lambda current: ExecutionOutcome(result={"ok": True}, auto_continue=True),
    )
    completed = store.complete_ir(lease.task_id, worker.execute(lease.ir), lease_epoch=lease.lease_epoch)

    assert completed["task"]["status"] == "succeeded"
    assert completed["enqueuedTask"] is None
    assert completed["continuationBlocked"] == "hop_limit"


def test_expired_lease_is_requeued_and_stale_worker_is_fenced(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    ir = CanonicalIR(goal="survive worker loss", project_id="agentmanager", capability="recover.step")
    store.submit_ir(ir)

    first_lease = store.lease_next_ir("worker-old", ["recover.step"])
    assert first_lease is not None
    with store._connect() as connection:
        connection.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00Z' WHERE task_id=?",
            (first_lease.task_id,),
        )

    second_lease = store.lease_next_ir("worker-new", ["recover.step"])
    assert second_lease is not None
    assert second_lease.task_id == first_lease.task_id

    old_worker = RemoteRuntimeWorker("worker-old")
    old_worker.register("recover.step", lambda current: {"worker": "old"})
    with pytest.raises(ValueError, match="STALE_LEASE_EPOCH"):
        store.complete_ir(first_lease.task_id, old_worker.execute(first_lease.ir), lease_epoch=first_lease.lease_epoch)

    new_worker = RemoteRuntimeWorker("worker-new")
    new_worker.register("recover.step", lambda current: {"worker": "new"})
    completed = store.complete_ir(second_lease.task_id, new_worker.execute(second_lease.ir), lease_epoch=second_lease.lease_epoch)
    assert completed["task"]["status"] == "succeeded"
    assert completed["task"]["result"]["runtime_id"] == "worker-new"


def test_expired_same_node_attempt_cannot_commit_after_reclaim(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "same-node.sqlite3")
    ir = CanonicalIR(goal="fence reincarnated worker", project_id="agentmanager", capability="recover.step")
    store.submit_ir(ir)
    old = store.lease_next_ir("worker-a", ["recover.step"])
    assert old is not None and old.lease_epoch == 1
    with store._connect() as connection:
        connection.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00Z' WHERE task_id=?",
            (old.task_id,),
        )
    new = store.lease_next_ir("worker-a", ["recover.step"])
    assert new is not None and new.lease_epoch == old.lease_epoch + 1
    worker = RemoteRuntimeWorker("worker-a")
    worker.register("recover.step", lambda current: {"ok": True})
    result = worker.execute(ir)
    with pytest.raises(ValueError, match="STALE_LEASE_EPOCH"):
        store.complete_ir(old.task_id, result, lease_epoch=old.lease_epoch)
    assert store.get_task(old.task_id)["status"] == "leased"
    completed = store.complete_ir(new.task_id, result, lease_epoch=new.lease_epoch)
    assert completed["task"]["status"] == "succeeded"
    with pytest.raises(ValueError):
        store.complete_ir(new.task_id, result, lease_epoch=new.lease_epoch)


def test_missing_epoch_fails_closed_before_mutation(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "missing-epoch.sqlite3")
    ir = CanonicalIR(goal="typed lease required", project_id="agentmanager", capability="work")
    store.submit_ir(ir)
    lease = store.lease_next_ir("worker-a", ["work"])
    assert lease
    worker = RemoteRuntimeWorker("worker-a")
    worker.register("work", lambda current: {"ok": True})
    with pytest.raises(ValueError, match="LEASE_EPOCH_REQUIRED"):
        store.complete_ir(lease.task_id, worker.execute(ir))
    assert store.get_task(lease.task_id)["status"] == "leased"


def test_existing_sqlite_tasks_gain_lease_epoch_without_reset(tmp_path: Path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    store = DistributedControlPlane(path)
    ir = CanonicalIR(goal="migrate existing tasks", project_id="agentmanager", capability="migrate")
    task = store.submit_ir(ir)
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE tasks RENAME TO tasks_current")
        db.execute("""CREATE TABLE tasks AS
            SELECT task_id, idempotency_key, capability, payload_json, project_id,
                   target_node_id, status, lease_until, result_json, created_at, updated_at
            FROM tasks_current""")
        db.execute("DROP TABLE tasks_current")
    reopened = DistributedControlPlane(path)
    assert reopened.get_task(task["taskId"])["leaseEpoch"] == 0
    lease = reopened.lease_next_ir("worker-a", ["migrate"])
    assert lease is not None and lease.lease_epoch == 1

from pathlib import Path
import json

import pytest

from agent_core.canonical_context import CanonicalContextStore
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayService
from agentos_node.remote_worker import build_default_worker


def seed_doc():
    return {
        "updated_at": "2026-08-27T00:00:00Z",
        "integration_branch": "feature/distributed-agentos-runtime",
        "write_policy": {
            "experimental_writes_to_main": "deny",
            "branch_required_for_writes": True,
        },
        "active_work": {
            "goal": "prove receipt-driven context",
            "integration_branch": "feature/distributed-agentos-runtime",
            "current_findings": ["native execution exists"],
            "next_actions": ["Validate Master Floor.", "Separate CI from execution."],
        },
    }


def test_checkpoint_is_durable_and_idempotent(tmp_path: Path):
    store = CanonicalContextStore(tmp_path / "core.sqlite3")
    store.seed("demo", seed_doc(), seed_revision="seed-1")
    first = store.checkpoint(
        "demo",
        checkpoint_id="receipt-1",
        task_id="task-1",
        completed_action="Validate Master Floor.",
        finding="gpt-5.4-mini low passed with no side effects.",
    )
    replay = store.checkpoint(
        "demo",
        checkpoint_id="receipt-1",
        task_id="ignored",
        completed_action="Separate CI from execution.",
        finding="must not apply",
    )
    assert replay == first
    restarted = CanonicalContextStore(tmp_path / "core.sqlite3")
    loaded = restarted.load("demo")
    assert loaded["_runtime_context"]["revision"] == 2
    assert loaded["active_work"]["next_actions"] == ["Separate CI from execution."]
    assert "must not apply" not in loaded["active_work"]["current_findings"]


def test_checkpoint_rejects_unproven_action(tmp_path: Path):
    store = CanonicalContextStore(tmp_path / "core.sqlite3")
    store.seed("demo", seed_doc())
    with pytest.raises(ValueError, match="not an active next_action"):
        store.checkpoint(
            "demo",
            checkpoint_id="receipt-x",
            task_id="task-x",
            completed_action="Invented work.",
            finding="fake evidence",
        )


def test_verified_receipt_advances_fresh_attach(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seed_path = tmp_path / "development-context.json"
    seed_path.write_text(json.dumps(seed_doc()), encoding="utf-8")
    original_seed = seed_path.read_text(encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_CONTEXTS_JSON", json.dumps({"demo": str(seed_path)}))

    control = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    gateway = DistributedGatewayService(control)
    before = gateway.attach({"project_id": "demo", "agent": {"history": "none"}})
    assert before["execution_context"]["next_action"] == "Validate Master Floor."
    assert before["execution_context"]["runtime_context"]["revision"] == 1

    submitted = gateway.submit_task({
        "project_id": "demo",
        "goal": "record verified Master Floor evidence",
        "capability": "agentos.context.checkpoint",
        "payload": {
            "completed_action": "Validate Master Floor.",
            "finding": "gpt-5.4-mini low passed with no side effects.",
        },
    })
    task_id = submitted["task"]["taskId"]
    lease = control.lease_ir_task(task_id, "oracle-core-node")
    assert lease is not None
    result = build_default_worker("oracle-core-node").execute(lease.ir)
    completed = control.complete_ir(task_id, result)
    assert completed["contextCheckpoint"]["revision"] == 2

    fresh = DistributedGatewayService(DistributedControlPlane(tmp_path / "control-plane.sqlite3"))
    after = fresh.attach({"project_id": "demo", "agent": {"history": "none"}})
    context = after["execution_context"]
    assert context["next_action"] == "Separate CI from execution."
    assert context["runtime_context"]["revision"] == 2
    assert "gpt-5.4-mini low passed" in " ".join(context["current_findings"])
    assert seed_path.read_text(encoding="utf-8") == original_seed


def test_invalid_checkpoint_cannot_leave_success_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seed_path = tmp_path / "development-context.json"
    seed_path.write_text(json.dumps(seed_doc()), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_PROJECT_CONTEXTS_JSON", json.dumps({"demo": str(seed_path)}))

    control = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    gateway = DistributedGatewayService(control)
    gateway.attach({"project_id": "demo", "agent": {"history": "none"}})
    submitted = gateway.submit_task({
        "project_id": "demo",
        "goal": "attempt an unproven context transition",
        "capability": "agentos.context.checkpoint",
        "payload": {
            "completed_action": "Invented work that was never active.",
            "finding": "fake evidence",
        },
    })
    task_id = submitted["task"]["taskId"]
    lease = control.lease_ir_task(task_id, "oracle-core-node")
    assert lease is not None
    result = build_default_worker("oracle-core-node").execute(lease.ir)
    assert result.status == "succeeded"

    with pytest.raises(ValueError, match="not an active next_action"):
        control.complete_ir(task_id, result)

    task = control.get_task(task_id)
    assert task["status"] == "leased"
    loaded = CanonicalContextStore(tmp_path / "control-plane.sqlite3").load("demo")
    assert loaded["_runtime_context"]["revision"] == 1

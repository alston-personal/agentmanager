import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.push_dispatch import ExactGitHubActionsDispatchTransport, ResilientRuntimeDispatcher
from agent_core.runtime_dispatcher import RuntimeTarget
from runtime_core.canonical_ir import CanonicalIR


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_github_wake_payload_contains_exact_task_id(tmp_path: Path):
    seen = {}

    def opener(request, timeout):
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    store = DistributedControlPlane(tmp_path / "dispatch.sqlite3")
    dispatcher = ResilientRuntimeDispatcher(store, dispatch_timeout_seconds=60)
    dispatcher.register_transport(ExactGitHubActionsDispatchTransport("token", opener=opener))
    dispatcher.register_target(
        RuntimeTarget(
            target_id="github-actions-worker",
            kind="github_actions",
            capabilities=("agentos.ir.validate",),
            config={
                "repository": "owner/repo",
                "workflow": "distributed-agentos-worker.yml",
                "ref": "feature/distributed-agentos-runtime",
                "control_plane_url": "https://agentos.example.test",
            },
        ),
        persist=False,
    )
    ir = CanonicalIR(
        goal="exact github wake",
        project_id="agentmanager",
        capability="agentos.ir.validate",
        context={"runtime_policy": {"prefer_push": True}},
    )
    task = store.submit_ir(ir)
    receipt = dispatcher.dispatch_task(task["taskId"])
    assert receipt["status"] == "dispatched"
    assert seen["body"]["inputs"]["task_id"] == task["taskId"]
    assert seen["body"]["inputs"]["runtime_id"] == "github-actions-worker"


def test_stale_dispatched_wake_can_retry_when_task_is_still_submitted(tmp_path: Path):
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return FakeResponse()

    store = DistributedControlPlane(tmp_path / "retry.sqlite3")
    dispatcher = ResilientRuntimeDispatcher(store, dispatch_timeout_seconds=1)
    dispatcher.register_transport(ExactGitHubActionsDispatchTransport("token", opener=opener))
    dispatcher.register_target(
        RuntimeTarget(
            target_id="github-actions-worker",
            kind="github_actions",
            capabilities=("agentos.ir.validate",),
            config={
                "repository": "owner/repo",
                "control_plane_url": "https://agentos.example.test",
            },
        ),
        persist=False,
    )
    ir = CanonicalIR(
        goal="retry stale wake",
        project_id="agentmanager",
        capability="agentos.ir.validate",
        context={"runtime_policy": {"prefer_push": True}},
    )
    task = store.submit_ir(ir)
    first = dispatcher.dispatch_task(task["taskId"])
    assert first["status"] == "dispatched"
    assert len(calls) == 1

    stale = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    with store._connect() as connection:
        connection.execute(
            "UPDATE runtime_dispatches SET updated_at=? WHERE task_id=?",
            (stale, task["taskId"]),
        )
    second = dispatcher.dispatch_task(task["taskId"])
    assert second["status"] == "dispatched"
    assert second["attempts"] == 2
    assert len(calls) == 2
    assert second["dispatchId"] == first["dispatchId"]

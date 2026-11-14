import json
from pathlib import Path

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.runtime_dispatcher import (
    DispatchTransport,
    GitHubActionsDispatchTransport,
    RuntimeDispatcher,
    RuntimeTarget,
)
from runtime_core.canonical_ir import CanonicalIR


class FakeTransport(DispatchTransport):
    kind = "fake"

    def __init__(self) -> None:
        self.calls = []

    def dispatch(self, *, target, task, ir, dispatch_id):
        self.calls.append(
            {
                "target": target.target_id,
                "task_id": task["taskId"],
                "ir_id": ir.ir_id,
                "dispatch_id": dispatch_id,
            }
        )
        return {"external_ref": f"fake:{dispatch_id}"}


def _target() -> RuntimeTarget:
    return RuntimeTarget(
        target_id="push-worker",
        kind="fake",
        capabilities=("ai.generate",),
        priority=10,
    )


def test_dispatcher_persists_and_deduplicates_push_dispatch(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    ir = CanonicalIR(
        goal="dispatch automatically",
        project_id="agentmanager",
        capability="ai.generate",
    )
    task = store.submit_ir(ir)

    transport = FakeTransport()
    dispatcher = RuntimeDispatcher(store)
    dispatcher.register_transport(transport)
    dispatcher.register_target(_target())

    first = dispatcher.dispatch_task(task["taskId"])
    second = dispatcher.dispatch_task(task["taskId"])

    assert first["status"] == "dispatched"
    assert second["status"] == "already_dispatched"
    assert first["dispatchId"] == second["dispatchId"]
    assert len(transport.calls) == 1
    assert store.get_task(task["taskId"])["targetNodeId"] == "push-worker"


def test_dispatcher_prefers_online_pull_node_unless_ir_requests_push(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    node = {
        "apiVersion": "agentos/v1",
        "kind": "Node",
        "metadata": {"id": "local-node"},
        "spec": {"capabilities": [{"name": "ai.generate"}]},
    }
    store.register_node(node)
    store.heartbeat("local-node")

    transport = FakeTransport()
    dispatcher = RuntimeDispatcher(store)
    dispatcher.register_transport(transport)
    dispatcher.register_target(_target())

    pull_ir = CanonicalIR(
        goal="use local first",
        project_id="agentmanager",
        capability="ai.generate",
    )
    pull_task = store.submit_ir(pull_ir)
    waiting = dispatcher.dispatch_task(pull_task["taskId"])
    assert waiting["status"] == "waiting_for_pull"
    assert waiting["onlineNodes"] == ["local-node"]
    assert transport.calls == []

    push_ir = CanonicalIR(
        goal="force push runtime",
        project_id="agentmanager",
        capability="ai.generate",
        context={"runtime_policy": {"prefer_push": True}},
    )
    push_task = store.submit_ir(push_ir)
    pushed = dispatcher.dispatch_task(push_task["taskId"])
    assert pushed["status"] == "dispatched"
    assert len(transport.calls) == 1


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b""


def test_github_actions_transport_sends_stable_runtime_and_dispatch_ids():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    transport = GitHubActionsDispatchTransport("secret-token", opener=opener)
    target = RuntimeTarget(
        target_id="github-actions-worker",
        kind="github_actions",
        capabilities=("agentos.ir.validate",),
        config={
            "repository": "alston-personal/agentmanager",
            "workflow": "distributed-agentos-worker.yml",
            "ref": "feature/distributed-agentos-runtime",
            "control_plane_url": "https://agentos.example.test",
        },
    )
    ir = CanonicalIR(
        goal="wake GitHub Actions",
        project_id="agentmanager",
        capability="agentos.ir.validate",
    )
    metadata = transport.dispatch(
        target=target,
        task={"taskId": "task-1"},
        ir=ir,
        dispatch_id="dispatch-1",
    )

    assert captured["url"].endswith(
        "/repos/alston-personal/agentmanager/actions/workflows/"
        "distributed-agentos-worker.yml/dispatches"
    )
    assert captured["payload"]["ref"] == "feature/distributed-agentos-runtime"
    assert captured["payload"]["inputs"]["runtime_id"] == "github-actions-worker"
    assert captured["payload"]["inputs"]["dispatch_id"] == "dispatch-1"
    assert captured["payload"]["inputs"]["control_plane_url"] == "https://agentos.example.test"
    assert metadata["http_status"] == 204


class FailingTransport(DispatchTransport):
    kind = "failing"

    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, *, target, task, ir, dispatch_id):
        self.calls += 1
        raise RuntimeError("wake failed")


def test_runtime_targets_survive_dispatcher_restart(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    first = RuntimeDispatcher(store)
    first.register_target(
        RuntimeTarget(
            target_id="persisted-worker",
            kind="fake",
            capabilities=("ai.generate",),
            priority=7,
            config={"endpoint": "https://example.test"},
        )
    )

    restarted = RuntimeDispatcher(store)
    targets = restarted.list_targets()

    assert targets[0]["targetId"] == "persisted-worker"
    assert targets[0]["capabilities"] == ["ai.generate"]
    assert targets[0]["priority"] == 7
    assert targets[0]["transportReady"] is False


def test_failed_dispatch_uses_retry_backoff(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "control-plane.sqlite3")
    ir = CanonicalIR(
        goal="retry safely",
        project_id="agentmanager",
        capability="ai.generate",
        context={"runtime_policy": {"prefer_push": True}},
    )
    task = store.submit_ir(ir)

    transport = FailingTransport()
    dispatcher = RuntimeDispatcher(store, dispatch_retry_seconds=60)
    dispatcher.register_transport(transport)
    dispatcher.register_target(
        RuntimeTarget(
            target_id="failing-worker",
            kind="failing",
            capabilities=("ai.generate",),
        )
    )

    first = dispatcher.dispatch_task(task["taskId"])
    second = dispatcher.dispatch_task(task["taskId"])

    assert first["status"] == "failed"
    assert second["status"] == "retry_wait"
    assert second["dispatchId"] == first["dispatchId"]
    assert transport.calls == 1


def test_dispatch_sweep_survives_transient_store_error_without_leaking_details(
    tmp_path, caplog, monkeypatch,
):
    """A one-off DB failure cannot permanently strand pending continuations."""
    import logging

    from agent_core.distributed_control_plane import DistributedControlPlane
    from agent_core.runtime_dispatcher import RuntimeDispatcher

    dispatcher = RuntimeDispatcher(DistributedControlPlane(tmp_path / "sweep.sqlite3"))
    calls = []

    def flaky_dispatch(*, limit):
        calls.append(limit)
        if len(calls) == 1:
            raise RuntimeError("private-webhook-token-do-not-log")
        return []

    monkeypatch.setattr(dispatcher, "dispatch_pending", flaky_dispatch)

    class ThreeCycles:
        def __init__(self):
            self.waits = 0

        def is_set(self):
            return self.waits >= 3

        def wait(self, interval):
            assert interval == 0.01
            self.waits += 1

    with caplog.at_level(logging.INFO):
        dispatcher.run_sweep_loop(ThreeCycles(), interval_seconds=0.01, limit=9)

    assert calls == [9, 9, 9]
    assert "runtime dispatch sweep failed (RuntimeError); retrying" in caplog.text
    assert "runtime dispatch sweep recovered" in caplog.text
    assert "private-webhook-token-do-not-log" not in caplog.text

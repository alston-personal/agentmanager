from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_core.controller_service import ControllerService
from agent_core.runtime_converge_contract import ALLOWED_REPOSITORY, SCHEMA
from agentos_node import runtime_converge_action_relay as relay


SHA = "a" * 40
PREVIOUS = "b" * 40


def request(**overrides):
    payload = {
        "schema": SCHEMA,
        "request_id": "ctl_runtime_1",
        "node_id": "oracle-core-node",
        "repository": ALLOWED_REPOSITORY,
        "source_ref": "core/integration",
        "source_commit": SHA,
    }
    payload.update(overrides)
    return payload


class Proc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def test_relay_registers_fixed_semantic_action_without_generic_carrier():
    assert relay.ACTION == "agentos.runtime.converge"
    assert relay.ACTION in relay.ACTIONS
    assert "shell.exec" not in relay.ACTIONS
    assert "argv" not in relay.SAFE_RESULT_FIELDS
    assert "stdout" not in relay.SAFE_RESULT_FIELDS
    assert "stderr" not in relay.SAFE_RESULT_FIELDS


def test_fixed_runtime_install_converges_product_employee_profile_after_realm(monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, *, cwd, timeout=180):
        calls.append((list(argv), cwd, timeout))
        return Proc(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(relay, "_run", fake_run)
    monkeypatch.setattr(relay, "_health", lambda: True)
    assert relay._install_fixed_runtime(tmp_path) is True
    assert calls == [
        (["python3", "scripts/install_services.py"], tmp_path, 240),
        (["bash", "scripts/install_realm_fabric_user.sh"], tmp_path, 120),
        (["bash", "scripts/activate_product_employees_oracle.sh"], tmp_path, 240),
    ]


def test_preflight_refuses_dirty_checkout(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()

    def fake_git_value(repo, *args):
        if args[:3] == ("remote", "get-url", "origin"):
            return "https://github.com/alston-personal/agentmanager.git"
        if args[:2] == ("status", "--porcelain"):
            return " M agent_core/realm_server.py"
        raise AssertionError(args)

    monkeypatch.setattr(relay, "_git_value", fake_git_value)
    result = relay.converge_runtime(request(), repo=tmp_path)
    assert result["status"] == "failed"
    assert result["classification"] == "tracked_checkout_dirty"
    assert result["credential_exposed"] is False


def test_preflight_refuses_requested_sha_that_is_not_exact_ref_head(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()

    def fake_git_value(repo, *args):
        if args[:3] == ("remote", "get-url", "origin"):
            return "git@github.com:alston-personal/agentmanager.git"
        if args[:2] == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return PREVIOUS
        if args == ("rev-parse", "FETCH_HEAD"):
            return "c" * 40
        raise AssertionError(args)

    monkeypatch.setattr(relay, "_git_value", fake_git_value)
    monkeypatch.setattr(relay, "_git", lambda *a, **k: Proc(returncode=0, stdout=""))
    result = relay.converge_runtime(request(), repo=tmp_path)
    assert result["classification"] == "exact_source_head_mismatch"


def test_health_failure_rolls_back_exact_previous_generation(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(relay, "_preflight", lambda repo, req: (PREVIOUS, False))
    checkouts = []
    monkeypatch.setattr(relay, "_checkout_exact", lambda repo, sha: checkouts.append(sha) or True)
    outcomes = iter([False, True])
    monkeypatch.setattr(relay, "_install_fixed_runtime", lambda repo: next(outcomes))
    result = relay.converge_runtime(request(), repo=tmp_path)
    assert checkouts == [SHA, PREVIOUS]
    assert result["classification"] == "TARGET_HEALTH_FAILED_ROLLED_BACK"
    assert result["rollback"] == "completed"
    assert result["resulting_commit"] == PREVIOUS


def test_rollback_ambiguity_is_unknown_and_not_success(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(relay, "_preflight", lambda repo, req: (PREVIOUS, False))
    monkeypatch.setattr(relay, "_checkout_exact", lambda repo, sha: True)
    monkeypatch.setattr(relay, "_install_fixed_runtime", lambda repo: False)
    result = relay.converge_runtime(request(), repo=tmp_path)
    assert result["classification"] == "ROLLBACK_OUTCOME_UNKNOWN"
    assert result["rollback"] == "unknown"
    assert result["status"] == "failed"


class NodeRegistry:
    def node_map(self):
        return {"nodes": [{"node_id": "oracle-core-node", "status": "online", "capabilities": ["node.runtime.converge"]}]}


class Fabric:
    node_registry = NodeRegistry()

    def queue_task(self, *args, **kwargs):
        raise AssertionError("runtime converge must not enter generic Node task queue")


class RuntimeDispatcher:
    def __init__(self):
        self.seen = None

    def submit(self, *, request):
        self.seen = request
        return {"ok": True, "action": "node.runtime.converge", "task_id": "action-123", "state": "queued"}


def test_controller_routes_typed_converge_to_fixed_relay_not_node_queue():
    dispatcher = RuntimeDispatcher()
    controller = ControllerService(Fabric(), runtime_converge_dispatcher=dispatcher)
    result = controller.dispatch({
        "node_id": "oracle-core-node",
        "task_id": "ctl_runtime_1",
        "action": "node.runtime.converge",
        "repository": ALLOWED_REPOSITORY,
        "source_ref": "core/integration",
        "source_commit": SHA,
    })
    assert result["task_id"] == "action-123"
    assert dispatcher.seen["request_id"] == "ctl_runtime_1"
    assert set(dispatcher.seen) == {"schema", "request_id", "node_id", "repository", "source_ref", "source_commit"}


@pytest.mark.parametrize("field", ["shell", "argv", "command", "module", "token", "environment"])
def test_controller_rejects_execution_carrier_fields(field):
    controller = ControllerService(Fabric(), runtime_converge_dispatcher=RuntimeDispatcher())
    body = {
        "node_id": "oracle-core-node",
        "action": "node.runtime.converge",
        "repository": ALLOWED_REPOSITORY,
        "source_ref": "core/integration",
        "source_commit": SHA,
        field: "forbidden",
    }
    with pytest.raises(ValueError):
        controller.dispatch(body)

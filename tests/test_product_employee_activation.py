from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agentos_node.employee_wake_node import (
    EMPLOYEE_IDS,
    NODE_ID,
    EmployeeWakeOnlyClient,
    bootstrap_local_enrollment,
)

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "bootstrap_product_employees.py"
ACTIVATE = ROOT / "scripts" / "activate_product_employees_oracle.sh"
WAKE_UNIT = ROOT / ".agent" / "scripts" / "agentos-employee-wake-node.service"

spec = importlib.util.spec_from_file_location("bootstrap_product_employees", BOOTSTRAP_PATH)
assert spec and spec.loader
bootstrap_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_mod)


def test_wake_only_client_advertises_exactly_one_capability(tmp_path: Path):
    client = EmployeeWakeOnlyClient("realm-test", NODE_ID, tmp_path / "wakes")
    manifest = client.capability_manifest()
    assert manifest["capabilities"] == ["agent.employee.wake.deliver"]
    assert manifest["workspace_roots"] == {"readable": [], "writable": []}
    assert manifest["tool_presence"] == {}


def test_wake_only_client_rejects_non_wake_action(tmp_path: Path):
    client = EmployeeWakeOnlyClient("realm-test", NODE_ID, tmp_path / "wakes")
    receipt = client.execute({
        "schema": "agentos.node-task/v0.1",
        "task_id": "task-1",
        "action": "shell.exec",
    })
    assert receipt["ok"] is False
    assert "action_not_allowed" in receipt["error"]
    assert receipt["credential_exposed"] is False
    assert receipt["executor_invoked"] is False


def test_local_wake_enrollment_is_idempotent_and_credential_file_is_private(tmp_path: Path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("AGENT_DATA_ROOT", str(data_root))
    registry = NodeRegistry(data_root / "realm" / "nodes.json")
    fabric = RealmFabricStore(data_root / "realm" / "fabric.json", node_registry=registry)
    fabric.initialize_realm("realm-test")
    registry.initialize_realm("realm-test")
    config_path = data_root / "employee-wake-node" / "client.json"
    wake_root = data_root / "employee-wakes"

    first = bootstrap_local_enrollment(data_root=data_root, config_path=config_path, wake_root=wake_root)
    second = bootstrap_local_enrollment(data_root=data_root, config_path=config_path, wake_root=wake_root)
    assert first.node_id == second.node_id == NODE_ID
    assert first.node_token == second.node_token
    assert (config_path.stat().st_mode & 0o777) == 0o600
    stored = fabric.load()
    assert NODE_ID in stored["nodes"]
    assert first.node_token not in json.dumps(stored)


def test_product_employee_bootstrap_is_idempotent_and_preserves_progress(tmp_path: Path):
    runtime_root = tmp_path / "employee-runtime"
    first = bootstrap_mod.bootstrap_all(runtime_root)
    assert first["ok"] is True
    runtime = EmployeeRuntime(runtime_root)
    assert {runtime.get_employee(e).agent_id for e in EMPLOYEE_IDS} == set(EMPLOYEE_IDS)
    runtime.update_assignment("zeus-writer-continuation-v1", thread_head="product:zeus-writer:progress-1")

    second = bootstrap_mod.bootstrap_all(runtime_root)
    zeus = next(x for x in second["employees"] if x["employee_id"] == "zeus-writer")
    assert zeus["employee_created"] is False
    assert zeus["assignment_created"] is False
    assert zeus["progress_preserved"] is True
    assert runtime.get_assignment("zeus-writer-continuation-v1").thread_head == "product:zeus-writer:progress-1"


def test_product_employee_bootstrap_never_reopens_terminal_assignment(tmp_path: Path):
    runtime_root = tmp_path / "employee-runtime"
    bootstrap_mod.bootstrap_all(runtime_root)
    runtime = EmployeeRuntime(runtime_root)
    runtime.update_assignment("youtube-ai-manager-scan-v1", state="completed", thread_head="product:youtube-ai-manager:done")
    receipt = bootstrap_mod.bootstrap_all(runtime_root)
    youtube = next(x for x in receipt["employees"] if x["employee_id"] == "youtube-ai-manager")
    assert youtube["terminal_preserved"] is True
    assert runtime.get_assignment("youtube-ai-manager-scan-v1").state == "completed"


def test_activation_assets_are_fixed_and_do_not_emit_verified_markers():
    shell = ACTIVATE.read_text(encoding="utf-8")
    unit = WAKE_UNIT.read_text(encoding="utf-8")
    assert 'WAKE_NODE_ID="oracle-employee-wake-node"' in shell
    assert 'AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1' in shell
    assert 'AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE=1' in shell
    assert 'verified_marker_emitted=false' in shell
    assert "shell.exec" not in unit
    assert "youtube" not in unit.casefold()
    assert "zeus" not in unit.casefold()
    assert "employee_wake_node" in unit

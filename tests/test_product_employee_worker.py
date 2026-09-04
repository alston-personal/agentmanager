from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos_node.employee_worker_host import WorkerHostCandidate
from agentos_node.employee_worker_host_runtime import (
    ExactEmployeeWorkerHost,
    ProductEmployeeWorkerAdapterRegistry,
)
from agentos_node.product_employee_worker import _require_runner_scope


def _capsule(employee_id: str, assignment_id: str, role_id: str, skill_id: str) -> dict:
    return {
        "schema": "agentos.employee-wake-delivery/v1",
        "wake_id": "wake-1",
        "employee_id": employee_id,
        "assignment_id": assignment_id,
        "node_id": "oracle-core-node",
        "presence_id": "presence-1",
        "presence_generation": 1,
        "expected_lease_generation": 1,
        "digest": "digest",
        "wake_intent": {
            "role_ids": [role_id],
            "skill_ids": [skill_id],
        },
        "employee_wake_route": {},
    }


def test_v2_registry_resolves_only_exact_product_scope() -> None:
    registry = ProductEmployeeWorkerAdapterRegistry()
    zeus = _capsule(
        "zeus-writer",
        "zeus-writer-continuation-v1",
        "product.zeus_writer",
        "writing.project.continue",
    )
    adapter = registry.resolve(zeus)
    assert adapter is not None
    assert adapter.runner_kind == "zeus_writer_v1"

    foreign = dict(zeus)
    foreign["wake_intent"] = dict(zeus["wake_intent"])
    foreign["wake_intent"]["role_ids"] = ["product.youtube_ai_manager"]
    assert registry.resolve(foreign) is None


def test_product_runner_scope_is_fail_closed() -> None:
    youtube = _capsule(
        "youtube-ai-manager",
        "youtube-ai-manager-scan-v1",
        "product.youtube_ai_manager",
        "youtube.optimization.scan",
    )
    scope = _require_runner_scope("youtube_ai_manager_scan_v1", youtube)
    assert scope["employee_id"] == "youtube-ai-manager"

    with pytest.raises(PermissionError, match="runner_kind_not_allowed"):
        _require_runner_scope("arbitrary_shell", youtube)


def test_exact_shared_host_maps_product_runner_to_fixed_cli(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    wake_root = tmp_path / "wake"
    host_root = tmp_path / "host"
    worker_root = tmp_path / "worker"
    for path in (runtime_root, wake_root, host_root, worker_root):
        path.mkdir()

    host = ExactEmployeeWorkerHost(
        runtime_root=runtime_root,
        wake_root=wake_root,
        host_state_root=host_root,
        worker_state_root=worker_root,
        node_id="oracle-core-node",
    )
    capsule = _capsule(
        "zeus-writer",
        "zeus-writer-continuation-v1",
        "product.zeus_writer",
        "writing.project.continue",
    )
    adapter = host.registry.resolve(capsule)
    assert adapter is not None
    host._pinned_candidate = WorkerHostCandidate(  # noqa: SLF001 - exact-host boundary test
        path=Path("wake.json"),
        capsule=capsule,
        adapter=adapter,
    )
    command = host._child_command(adapter)  # noqa: SLF001
    joined = " ".join(command)
    assert "agentos_node.product_employee_worker_cli" in joined
    assert "--runner-kind zeus_writer_v1" in joined
    assert "--wake-id wake-1" in joined
    assert "--presence-generation 1" in joined
    assert "shell" not in joined


def test_shared_host_accepts_only_runner_specific_result_schema(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("runtime", "wake", "host", "worker")]
    for path in roots:
        path.mkdir()
    host = ExactEmployeeWorkerHost(
        runtime_root=roots[0],
        wake_root=roots[1],
        host_state_root=roots[2],
        worker_state_root=roots[3],
        node_id="oracle-core-node",
    )
    capsule = _capsule(
        "youtube-ai-manager",
        "youtube-ai-manager-scan-v1",
        "product.youtube_ai_manager",
        "youtube.optimization.scan",
    )
    adapter = host.registry.resolve(capsule)
    assert adapter is not None
    host._pinned_candidate = WorkerHostCandidate(Path("wake.json"), capsule, adapter)  # noqa: SLF001
    good = {
        "schema": "agentos.youtube-ai-manager-scan-worker-cli-result/v1",
        "status": "checkpointed",
        "work_performed": True,
        "employee_id": "youtube-ai-manager",
        "assignment_id": "youtube-ai-manager-scan-v1",
        "wake_id": "wake-1",
        "presence_generation": 1,
        "lease_generation": 1,
        "thread_head": "dry-run",
        "error_code": None,
        "executor_provider": "unbound",
        "executor_model": "",
        "credential_exposed": False,
        "session_identity_exposed": False,
        "verified_marker_emitted": False,
    }
    assert host._parse_child_result(json.dumps(good)) is not None  # noqa: SLF001
    good["schema"] = "agentos.zeus-writer-worker-cli-result/v1"
    assert host._parse_child_result(json.dumps(good)) is None  # noqa: SLF001

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentos_node.employee_worker_host_runtime as worker_runtime
import agentos_node.product_employee_worker as product_worker
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


def test_product_host_waits_for_s4_awaiting_claim_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    employee_wake_root = wake_root / "zeus-writer"
    employee_wake_root.mkdir()
    (employee_wake_root / "wake-1.json").write_text(json.dumps(capsule), encoding="utf-8")

    def not_ready(*args, **kwargs):
        raise PermissionError("product_employee_worker_governed_delivery_missing")

    monkeypatch.setattr(worker_runtime, "require_governed_product_delivery", not_ready)
    assert host.process_one() is None
    assert list((host_root / "dispatches").glob("*/*.json")) == []

    monkeypatch.setattr(worker_runtime, "require_governed_product_delivery", lambda *args, **kwargs: {"status": "awaiting_claim"})
    candidates = host._candidates()  # noqa: SLF001 - prelaunch race boundary test
    assert len(candidates) == 1
    assert candidates[0].capsule["wake_id"] == "wake-1"
    assert list((host_root / "dispatches").glob("*/*.json")) == []



def test_zeus_review_receipt_is_persisted_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    roots = [tmp_path / name for name in ("runtime", "wake", "host", "worker")]
    for path in roots:
        path.mkdir()
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=roots[0],
        wake_root=roots[1],
        worker_state_root=roots[3],
        node_id="oracle-core-node",
        runner_kind="zeus_writer_v1",
    )
    work_ref = {
        "schema": "agentos.employee-work-intent-ref/v1",
        "product_id": "zeus-writer",
        "state_key": "current-work",
        "revision": 1,
        "digest": "sha256:" + "a" * 64,
    }
    receipt = {
        "schema": "agentos.execution-receipt/v1",
        "result_status": "success",
        "evidence": {
            "chapter": "Ch05",
            "work_intent_digest": work_ref["digest"],
            "mutation_performed": False,
            "publish_performed": False,
            "credential_exposed": False,
        },
        "credential_exposed": False,
    }
    monkeypatch.setattr(product_worker, "execute_bound_work_intent", lambda ref: receipt if ref == work_ref else None)
    returned = worker._execute_zeus_review(  # noqa: SLF001
        work_ref,
        employee_id="zeus-writer",
        wake_id="wake-review-1",
        presence_generation=7,
    )
    assert returned == receipt
    persisted = roots[3] / "product-receipts" / "zeus-writer" / "wake-review-1.p000007.json"
    assert persisted.is_file()
    payload = json.loads(persisted.read_text(encoding="utf-8"))
    assert payload["result_status"] == "success"
    assert payload["evidence"]["mutation_performed"] is False
    assert payload["evidence"]["publish_performed"] is False


def test_zeus_review_failure_is_not_treated_as_checkpoint_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    roots = [tmp_path / name for name in ("runtime", "wake", "host", "worker")]
    for path in roots:
        path.mkdir()
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=roots[0],
        wake_root=roots[1],
        worker_state_root=roots[3],
        node_id="oracle-core-node",
        runner_kind="zeus_writer_v1",
    )
    work_ref = {
        "schema": "agentos.employee-work-intent-ref/v1",
        "product_id": "zeus-writer",
        "state_key": "current-work",
        "revision": 1,
        "digest": "sha256:" + "b" * 64,
    }
    monkeypatch.setattr(
        product_worker,
        "execute_bound_work_intent",
        lambda ref: {
            "schema": "agentos.execution-receipt/v1",
            "result_status": "failed",
            "error_code": "zeus_review_work_ref_mismatch",
            "evidence": {},
            "credential_exposed": False,
        },
    )
    receipt = worker._execute_zeus_review(  # noqa: SLF001
        work_ref,
        employee_id="zeus-writer",
        wake_id="wake-review-2",
        presence_generation=8,
    )
    assert receipt["result_status"] == "failed"
    assert receipt["error_code"] == "zeus_review_work_ref_mismatch"


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

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentos_node.employee_worker_host_runtime as worker_runtime
from agent_core.employee_runtime import EmployeeRuntime
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


def _materialize_governed_delivery(runtime_root: Path, capsule: dict, reconcile_id: str = "reconcile_test") -> None:
    deliveries = runtime_root / "supervisor" / "deliveries"
    intents = runtime_root / "supervisor" / "intents"
    deliveries.mkdir(parents=True, exist_ok=True)
    intents.mkdir(parents=True, exist_ok=True)
    delivery = {
        "schema": product_worker.DELIVERY_STATE_SCHEMA,
        "status": "awaiting_claim",
        "employee_id": capsule["employee_id"],
        "assignment_id": capsule["assignment_id"],
        "wake_id": capsule["wake_id"],
        "transport": product_worker.EXPECTED_TRANSPORT,
        "authority_policy_id": product_worker.EXPECTED_AUTHORITY_POLICY,
        "capability": product_worker.WAKE_CAPABILITY,
        "dispatch_performed": True,
        "node_id": capsule["node_id"],
        "presence_id": capsule["presence_id"],
        "presence_generation": capsule["presence_generation"],
        "task_id": "task-1",
        "wake_attempt_id": "attempt-1",
        "reconcile_id": reconcile_id,
    }
    intent = {
        "schema": product_worker.INTENT_RECORD_SCHEMA,
        "reconcile_id": reconcile_id,
        "state": "planned",
        "dispatch_performed": False,
        "intent": {
            "schema": product_worker.RECONCILE_INTENT_SCHEMA,
            "kind": "employee_wake",
            "employee_id": capsule["employee_id"],
            "assignment_id": capsule["assignment_id"],
            "authority_boundary": "observe_and_select_only",
            "node_selection": "unbound",
            "executor_selection": "unbound",
            "transport_selection": "unbound",
            "capability_authority": "unbound",
            "credential_exposed": False,
            "wake_intent": capsule["wake_intent"],
        },
    }
    (deliveries / f"{reconcile_id}.json").write_text(json.dumps(delivery), encoding="utf-8")
    (intents / f"{reconcile_id}.json").write_text(json.dumps(intent), encoding="utf-8")


def test_governed_delivery_index_reuses_unchanged_evidence_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule = _capsule(
        "zeus-writer",
        "zeus-writer-continuation-v1",
        "product.zeus_writer",
        "writing.project.continue",
    )
    _materialize_governed_delivery(tmp_path, capsule)
    product_worker._GOVERNED_DELIVERY_INDEX_CACHE.clear()

    first = product_worker.require_governed_product_delivery(tmp_path, "zeus_writer_v1", capsule)
    assert first["reconcile_id"] == "reconcile_test"

    monkeypatch.setattr(product_worker, "_read", lambda path: (_ for _ in ()).throw(AssertionError("evidence reread")))
    second = product_worker.require_governed_product_delivery(tmp_path, "zeus_writer_v1", capsule)
    assert second["reconcile_id"] == "reconcile_test"


def test_governed_delivery_index_invalidates_when_evidence_directory_changes(tmp_path: Path) -> None:
    capsule = _capsule(
        "zeus-writer",
        "zeus-writer-continuation-v1",
        "product.zeus_writer",
        "writing.project.continue",
    )
    _materialize_governed_delivery(tmp_path, capsule, "reconcile_one")
    product_worker._GOVERNED_DELIVERY_INDEX_CACHE.clear()
    assert product_worker.require_governed_product_delivery(tmp_path, "zeus_writer_v1", capsule)["reconcile_id"] == "reconcile_one"

    _materialize_governed_delivery(tmp_path, capsule, "reconcile_two")
    with pytest.raises(PermissionError, match="governed_delivery_ambiguous"):
        product_worker.require_governed_product_delivery(tmp_path, "zeus_writer_v1", capsule)


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


def _materialize_product_assignment(root: Path, *, employee_id: str, assignment_id: str, role_id: str, skill_id: str) -> EmployeeRuntime:
    runtime = EmployeeRuntime(root)
    runtime.create_employee(employee_id, employee_id, role_ids=[role_id], skill_ids=[skill_id])
    runtime.create_assignment(assignment_id, employee_id, "bounded product acceptance")
    return runtime


def test_youtube_missing_governed_read_adapter_finishes_blocked_instead_of_lease_churn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "runtime"
    wake_root = tmp_path / "wake"
    worker_root = tmp_path / "worker"
    for item in (runtime_root, wake_root, worker_root):
        item.mkdir()
    runtime = _materialize_product_assignment(
        runtime_root,
        employee_id="youtube-ai-manager",
        assignment_id="youtube-ai-manager-scan-v1",
        role_id="product.youtube_ai_manager",
        skill_id="youtube.optimization.scan",
    )
    capsule = _capsule(
        "youtube-ai-manager",
        "youtube-ai-manager-scan-v1",
        "product.youtube_ai_manager",
        "youtube.optimization.scan",
    )
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=runtime_root,
        wake_root=wake_root,
        worker_state_root=worker_root,
        node_id="oracle-core-node",
        runner_kind="youtube_ai_manager_scan_v1",
    )
    monkeypatch.setattr(product_worker, "require_governed_product_delivery", lambda *args, **kwargs: {"status": "awaiting_claim"})
    monkeypatch.setattr(worker, "_capsules", lambda: [(Path("wake.json"), capsule)])

    state = worker.process_exact(wake_id="wake-1", presence_generation=1)
    assert state is not None
    assert state.status == "blocked"
    assert state.error_code == "youtube_governed_read_adapter_unavailable"
    assert runtime.get_assignment("youtube-ai-manager-scan-v1").state == "blocked"
    receipt = json.loads(
        (runtime_root / "lifecycle" / "receipts" / "youtube-ai-manager-scan-v1" / "000001.json").read_text(encoding="utf-8")
    )
    assert receipt["outcome"] == "blocked"
    assert receipt["result_summary"]["external_api_read_performed"] is False
    assert receipt["result_summary"]["external_api_mutation_performed"] is False


def test_zeus_safe_review_finishes_handoff_with_terminal_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "runtime"
    wake_root = tmp_path / "wake"
    worker_root = tmp_path / "worker"
    for item in (runtime_root, wake_root, worker_root):
        item.mkdir()
    runtime = _materialize_product_assignment(
        runtime_root,
        employee_id="zeus-writer",
        assignment_id="zeus-writer-continuation-v1",
        role_id="product.zeus_writer",
        skill_id="writing.project.continue",
    )
    capsule = _capsule(
        "zeus-writer",
        "zeus-writer-continuation-v1",
        "product.zeus_writer",
        "writing.project.continue",
    )
    work_ref = {
        "schema": "agentos.employee-work-intent-ref/v1",
        "product_id": "zeus-writer",
        "state_key": "current-work",
        "revision": 1,
        "digest": "sha256:" + "a" * 64,
    }
    capsule["wake_intent"]["work_intent_ref"] = work_ref
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=runtime_root,
        wake_root=wake_root,
        worker_state_root=worker_root,
        node_id="oracle-core-node",
        runner_kind="zeus_writer_v1",
    )
    monkeypatch.setattr(product_worker, "require_governed_product_delivery", lambda *args, **kwargs: {"status": "awaiting_claim"})
    monkeypatch.setattr(worker, "_capsules", lambda: [(Path("wake.json"), capsule)])
    monkeypatch.setattr(
        worker,
        "_execute_zeus_review",
        lambda *args, **kwargs: {
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
        },
    )

    state = worker.process_exact(wake_id="wake-1", presence_generation=1)
    assert state is not None
    assert state.status == "handoff"
    assert state.error_code is None
    assert runtime.get_assignment("zeus-writer-continuation-v1").state == "handoff"
    receipt = json.loads(
        (runtime_root / "lifecycle" / "receipts" / "zeus-writer-continuation-v1" / "000001.json").read_text(encoding="utf-8")
    )
    assert receipt["outcome"] == "handoff"
    assert receipt["result_summary"]["mutation_performed"] is False
    assert receipt["result_summary"]["publish_performed"] is False
    assert receipt["result_summary"]["next_authority_required"] == "zeus-product-draft-mutation"


def test_worker_host_preserves_trusted_blocked_terminal_result(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("runtime", "wake", "host", "worker")]
    for item in roots:
        item.mkdir()
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
    candidate = WorkerHostCandidate(Path("wake.json"), capsule, adapter)
    host._pinned_candidate = candidate  # noqa: SLF001
    payload = {
        "schema": "agentos.youtube-ai-manager-scan-worker-cli-result/v1",
        "status": "blocked",
        "work_performed": True,
        "employee_id": "youtube-ai-manager",
        "assignment_id": "youtube-ai-manager-scan-v1",
        "wake_id": "wake-1",
        "presence_generation": 1,
        "lease_generation": 1,
        "thread_head": "blocked",
        "error_code": "youtube_governed_read_adapter_unavailable",
        "executor_provider": "unbound",
        "executor_model": "",
        "credential_exposed": False,
        "session_identity_exposed": False,
        "verified_marker_emitted": False,
    }
    state = host._new_dispatch(candidate)  # noqa: SLF001
    result = host._reconcile_child_result(  # noqa: SLF001
        candidate,
        state,
        returncode=0,
        stdout=json.dumps(payload),
    )
    assert result["status"] == "blocked"
    assert result["error_code"] is None


def test_paw_is_registered_with_existing_wake_node_presence():
    from agentos_node.employee_wake_node import EMPLOYEE_IDS
    from agentos_node.product_employee_worker import SUPPORTED_PRODUCT_RUNNERS
    from agentos_node.employee_worker_host_runtime import V2_RUNNER_KINDS
    assert "the-paw" in EMPLOYEE_IDS
    assert len(EMPLOYEE_IDS) == len(set(EMPLOYEE_IDS))
    assert SUPPORTED_PRODUCT_RUNNERS["paw_inspect_v1"]["employee_id"] == "the-paw"
    assert "paw_inspect_v1" in V2_RUNNER_KINDS

def test_paw_signed_request_worker_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import hashlib
    import hmac
    import os
    from agentos_node.paw_engineering_request import SCHEMA, canonical_payload
    runtime_root, wake_root, worker_root = [tmp_path / name for name in ("runtime", "wake", "worker")]
    for root in (runtime_root, wake_root, worker_root):
        root.mkdir()
    runtime = _materialize_product_assignment(
        runtime_root, employee_id="the-paw", assignment_id="paw-470-inspection-v1",
        role_id="sector.paw", skill_id="engineering.work.inspect",
    )
    capsule = _capsule("the-paw", "paw-470-inspection-v1", "sector.paw", "engineering.work.inspect")
    capsule["wake_id"] = "wake_" + "a" * 24
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=runtime_root, wake_root=wake_root, worker_state_root=worker_root,
        node_id="oracle-core-node", runner_kind="paw_inspect_v1",
    )
    authority = worker_root / "trusted-engineering-authority"
    authority.mkdir(mode=0o700)
    key = b"trusted-paw-issuer-key-with-sufficient-length"
    key_file = authority / "paw-470-issuer.key"
    key_file.write_bytes(key)
    key_file.chmod(0o600)
    request = {
        "schema": SCHEMA, "grant": {"work_id": "issue-470-a"},
        "expected_sha256": "a" * 64, "replacement": "def test_x(): pass",
        "signature": "",
    }
    request["signature"] = hmac.new(key, canonical_payload(request), hashlib.sha256).hexdigest()
    request_file = authority / "paw-470-request.json"
    request_file.write_text(json.dumps(request))
    request_file.chmod(0o600)
    observed = {}
    def executor(**kwargs):
        observed.update(kwargs)
        from types import SimpleNamespace
        return SimpleNamespace(work_id="issue-470-a", base_sha="a" * 40, changed_file="tests/test_paw_engineering_worktree.py", commit_sha="b" * 40, branch="paw/470/issue-470-a")
    import agentos_node.paw_engineering_executor as paw_exec
    monkeypatch.setattr(paw_exec, "run_signed_paw_candidate", executor)
    import agentos_node.paw_engineering_bundle as paw_bundle
    monkeypatch.setattr(paw_bundle, "export_paw_bundle", lambda **kwargs: kwargs["destination"])
    monkeypatch.setattr(product_worker, "require_governed_product_delivery", lambda *args, **kwargs: {"status": "awaiting_claim"})
    monkeypatch.setattr(worker, "_capsules", lambda: [(Path("wake.json"), capsule)])
    state = worker.process_exact(wake_id=capsule["wake_id"], presence_generation=1)
    assert state.status == "handoff"
    assert observed["trusted_lease_generation"] == 1
    assert observed["trusted_wake_id"] == capsule["wake_id"]
    assert observed["request"]["signature"] == request["signature"]
    receipt = json.loads((runtime_root / "lifecycle" / "receipts" / "paw-470-inspection-v1" / "000001.json").read_text())
    assert receipt["outcome"] == "handoff"
    assert receipt["result_summary"]["independent_acceptance_pass"] is False
    assert receipt["result_summary"]["published"] is False

def test_paw_worker_real_executor_local_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import hashlib
    import subprocess
    
    from agentos_node.paw_engineering_request import issue_paw_request
    from agent_core.employee_lifecycle import EmployeeLifecycle
    from agentos_node.paw_engineering_grant import PawEngineeringGrant
    from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError
    real_root = Path(product_worker.__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    repo.mkdir()
    for path in (".agent/roles/registry.yaml", "governance/employee-skills.json", "governance/execution-authority.json"):
        dst = repo / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((real_root / path).read_bytes())
    source = repo / "tests/test_paw_engineering_worktree.py"
    source.parent.mkdir(parents=True)
    source.write_text("def test_one():\n    assert True\n")
    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()
    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("add", ".")
    git("commit", "-m", "fixture")
    base = git("rev-parse", "HEAD")
    runtime_root, wake_root, worker_root = [tmp_path / name for name in ("runtime", "wake", "worker")]
    for root in (runtime_root, wake_root, worker_root):
        root.mkdir()
    runtime = _materialize_product_assignment(
        runtime_root, employee_id="the-paw", assignment_id="paw-470-inspection-v1",
        role_id="sector.paw", skill_id="engineering.work.inspect",
    )
    capsule = _capsule("the-paw", "paw-470-inspection-v1", "sector.paw", "engineering.work.inspect")
    capsule["wake_id"] = "wake_" + "a" * 24
    grant = {
        "schema": "agentos.paw-engineering-grant/v1",
        "work_id": "issue-470-real", "assignment_id": "paw-470-inspection-v1",
        "wake_id": capsule["wake_id"], "presence_generation": 1, "lease_generation": 1,
        "repository_id": "alston-personal/agentmanager", "base_sha": base,
        "allowed_path": "tests/test_paw_engineering_worktree.py",
        "action": "prepare-static-test-candidate",
    }
    authority = worker_root / "trusted-engineering-authority"
    authority.mkdir(mode=0o700)
    key = b"isolated-test-control-plane-secret-key-00001"
    key_file = authority / "paw-470-issuer.key"
    key_file.write_bytes(key)
    key_file.chmod(0o600)
    # Issue against a genuinely active lease. Same claim ID is idempotent.
    lifecycle = EmployeeLifecycle(runtime)
    lease_id = "product-paw_inspect_v1-" + capsule["wake_id"] + "-1"
    lifecycle.claim("paw-470-inspection-v1", "the-paw", lease_id, lease_seconds=300)
    signed = issue_paw_request(
        grant=grant, expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        replacement="def test_one():\n    assert True\n\ndef test_two():\n    assert 2 + 2 == 4\n",
        issuer_key=key, trusted_assignment_id="paw-470-inspection-v1",
        trusted_wake_id=capsule["wake_id"], trusted_presence_generation=1,
        trusted_lease_generation=1, lifecycle=lifecycle, trusted_lease_id=lease_id,
        registry_path=repo / "governance/execution-authority.json",
    )
    request_file = authority / "paw-470-request.json"
    request_file.write_text(json.dumps(signed))
    request_file.chmod(0o600)
    monkeypatch.setattr(product_worker, "__file__", str(repo / "agentos_node/product_employee_worker.py"))
    monkeypatch.setattr(product_worker, "require_governed_product_delivery", lambda *args, **kwargs: {"status": "awaiting_claim"})
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=runtime_root, wake_root=wake_root, worker_state_root=worker_root,
        node_id="oracle-core-node", runner_kind="paw_inspect_v1", lease_seconds=300,
    )
    monkeypatch.setattr(worker, "_capsules", lambda: [(Path("wake.json"), capsule)])
    state = worker.process_exact(wake_id=capsule["wake_id"], presence_generation=1)
    assert state.status == "handoff"
    receipt = json.loads((runtime_root / "lifecycle/receipts/paw-470-inspection-v1/000001.json").read_text())
    commit_sha = receipt["result_summary"]["commit_sha"]
    assert receipt["result_summary"]["published"] is False
    assert receipt["result_summary"]["independent_acceptance_pass"] is False
    assert git("rev-parse", "HEAD") == base
    result_repo = worker_root / "paw-470-worktrees/issue-470-real"
    result_head = subprocess.run(["git", "-C", str(result_repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
    assert result_head == commit_sha


def test_dynamic_paw_b_requires_canonical_projection_and_governed_delivery(tmp_path: Path) -> None:
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    runtime = EmployeeRuntime(tmp_path)
    runtime.create_employee(
        "the-paw", "Paw", role_ids=["sector.paw"],
        skill_ids=["engineering.work.inspect"],
    )
    capsule = _capsule("the-paw", "paw-b", "sector.paw", "engineering.work.inspect")
    with pytest.raises(PermissionError, match="product_employee_worker_scope_mismatch"):
        _require_runner_scope("paw_inspect_v1", capsule, runtime_root=tmp_path)
    store = WorkItemStore(runtime)
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "b-independent",
        "source_kind": "canonical_state", "source_ref": "task:b-independent",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "Inspect independent B",
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    with pytest.raises(PermissionError):
        _require_runner_scope("paw_inspect_v1", capsule, runtime_root=tmp_path)
    store.project_pending_assignment("b-independent")
    assert _require_runner_scope("paw_inspect_v1", capsule, runtime_root=tmp_path)["employee_id"] == "the-paw"
    with pytest.raises(PermissionError):
        product_worker.require_governed_product_delivery(tmp_path, "paw_inspect_v1", capsule)
    _materialize_governed_delivery(tmp_path, capsule)
    assert product_worker.require_governed_product_delivery(tmp_path, "paw_inspect_v1", capsule)
    forged = dict(capsule, assignment_id="paw-b-forged")
    with pytest.raises(PermissionError):
        _require_runner_scope("paw_inspect_v1", forged, runtime_root=tmp_path)



def test_dynamic_paw_b_claims_and_writes_real_blocked_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    runtime_root, wake_root, worker_root = [tmp_path / name for name in ("runtime", "wake", "worker")]
    for root in (runtime_root, wake_root, worker_root):
        root.mkdir()
    runtime = EmployeeRuntime(runtime_root)
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    store = WorkItemStore(runtime)
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "independent-b",
        "source_kind": "canonical_state", "source_ref": "task:independent-b",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "Inspect B",
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    store.project_pending_assignment("independent-b")
    capsule = _capsule("the-paw", "paw-b", "sector.paw", "engineering.work.inspect")
    _materialize_governed_delivery(runtime_root, capsule)
    worker = product_worker.GovernedProductEmployeeWorker(
        runtime_root=runtime_root, wake_root=wake_root,
        worker_state_root=worker_root, node_id="oracle-core-node",
        runner_kind="paw_inspect_v1",
    )
    monkeypatch.setattr(worker, "_capsules", lambda: [(Path("wake.json"), capsule)])
    state = worker.process_exact(wake_id="wake-1", presence_generation=1)
    assert state is not None
    assert state.assignment_id == "paw-b"
    assert runtime.get_assignment("paw-b").state in {"blocked", "handoff"}
    receipt_path = runtime_root / "lifecycle/receipts/paw-b/000001.json"
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text())
    assert receipt["assignment_id"] == "paw-b"
    assert receipt["outcome"] == runtime.get_assignment("paw-b").state

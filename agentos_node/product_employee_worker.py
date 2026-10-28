from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry
from agent_core.employee_skills import EmployeeSkillRegistry, EmployeeSkillService
from agent_core.governed_execution import execute_bound_work_intent
from agent_core.executor_job_contract import canonical_executor_job_request
from agentos_node.completion_470_status_provider import inspect_completion_470

def _await_paw_request_after_claim(request_file: Path, public_file: Path, *, timeout_seconds: float = 8.0) -> None:
    """Bounded rendezvous with an independent issuer after claim.

    No request is synthesized or signed here. An absent issuer fails closed,
    preserving the ordinary blocked outcome. The issuer publishes atomically.
    """
    import time
    # The verifier may be provisioned just after a fresh Lease is claimed.
    # Wait for both independently owned artifacts; the worker never creates either.
    deadline = time.monotonic() + max(0.0, min(float(timeout_seconds), 8.0))
    while not (request_file.is_file() and public_file.is_file()) and time.monotonic() < deadline:
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


EXPECTED_AUTHORITY_POLICY = "core-supervisor-employee-wake-v1"
EXPECTED_TRANSPORT = "one_direct"
ELIGIBLE_PRECLAIM_DELIVERY_STATES = {"awaiting_claim"}
_GOVERNED_DELIVERY_INDEX_CACHE: dict[
    str,
    tuple[
        tuple[int, int, int, int],
        dict[tuple[str, str, str, str, str, int, str], list[dict[str, Any]]],
    ],
] = {}

SUPPORTED_PRODUCT_RUNNERS = {
    "paw_inspect_v1": {"employee_id": "the-paw", "assignment_id": "paw-470-inspection-v1", "role_ids": {"sector.paw"}, "skill_ids": {"engineering.work.inspect"}},
    "zeus_writer_v1": {
        "employee_id": "zeus-writer",
        "assignment_id": "zeus-writer-continuation-v1",
        "role_ids": {"product.zeus_writer"},
        "skill_ids": {"writing.project.continue"},
    },
    "youtube_ai_manager_scan_v1": {
        "employee_id": "youtube-ai-manager",
        "assignment_id": "youtube-ai-manager-scan-v1",
        "role_ids": {"product.youtube_ai_manager"},
        "skill_ids": {"youtube.optimization.scan"},
    },
}


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("product_employee_worker_evidence_invalid")
    return payload


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _same_wake(left: Any, right: Any) -> bool:
    return isinstance(left, dict) and isinstance(right, dict) and left == right


def _require_runner_scope(runner_kind: str, capsule: dict[str, Any], *, runtime_root: Path | None = None) -> dict[str, Any]:
    scope = SUPPORTED_PRODUCT_RUNNERS.get(str(runner_kind or "").strip())
    if scope is None:
        raise PermissionError("product_employee_runner_kind_not_allowed")
    wake = capsule.get("wake_intent")
    if not isinstance(wake, dict):
        raise PermissionError("product_employee_worker_wake_missing")
    if capsule.get("employee_id") != scope["employee_id"]:
        raise PermissionError("product_employee_worker_scope_mismatch")
    if capsule.get("assignment_id") != scope["assignment_id"]:
        if runner_kind != "paw_inspect_v1" or runtime_root is None:
            raise PermissionError("product_employee_worker_scope_mismatch")
        from agentos_node.employee_worker_host_runtime import ProductEmployeeWorkerAdapterRegistry
        adapter = ProductEmployeeWorkerAdapterRegistry(runtime_root=runtime_root).resolve(capsule)
        if adapter is None or adapter.assignment_id != capsule.get("assignment_id"):
            raise PermissionError("product_employee_worker_scope_mismatch")
    if set(wake.get("role_ids") or []) != scope["role_ids"]:
        raise PermissionError("product_employee_worker_role_scope_mismatch")
    if set(wake.get("skill_ids") or []) != scope["skill_ids"]:
        raise PermissionError("product_employee_worker_skill_scope_mismatch")
    return scope


def _wake_fingerprint(wake: Any) -> str:
    if not isinstance(wake, dict):
        return ""
    raw = json.dumps(wake, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()


def _evidence_signature(deliveries: Path, intents: Path) -> tuple[int, int, int, int]:
    ds = deliveries.stat()
    ins = intents.stat()
    return (ds.st_mtime_ns, ds.st_ctime_ns, ins.st_mtime_ns, ins.st_ctime_ns)


def _delivery_index_key(
    *,
    employee_id: Any,
    assignment_id: Any,
    wake_id: Any,
    node_id: Any,
    presence_id: Any,
    presence_generation: Any,
    wake: Any,
) -> tuple[str, str, str, str, str, int, str]:
    return (
        str(employee_id or ""),
        str(assignment_id or ""),
        str(wake_id or ""),
        str(node_id or ""),
        str(presence_id or ""),
        int(presence_generation or 0),
        _wake_fingerprint(wake),
    )


def _governed_delivery_index(
    root: Path,
) -> dict[tuple[str, str, str, str, str, int, str], list[dict[str, Any]]]:
    deliveries = root / "supervisor" / "deliveries"
    intents = root / "supervisor" / "intents"
    if not deliveries.is_dir() or not intents.is_dir():
        return {}

    try:
        signature = _evidence_signature(deliveries, intents)
    except OSError:
        return {}

    cache_key = str(root)
    cached = _GOVERNED_DELIVERY_INDEX_CACHE.get(cache_key)
    if cached is not None and cached[0] == signature:
        return cached[1]

    index: dict[tuple[str, str, str, str, str, int, str], list[dict[str, Any]]] = {}
    for path in sorted(deliveries.glob("reconcile_*.json")):
        try:
            delivery = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not delivery or delivery.get("schema") != DELIVERY_STATE_SCHEMA:
            continue
        if delivery.get("status") not in ELIGIBLE_PRECLAIM_DELIVERY_STATES:
            continue
        if delivery.get("transport") != EXPECTED_TRANSPORT:
            continue
        if delivery.get("authority_policy_id") != EXPECTED_AUTHORITY_POLICY:
            continue
        if delivery.get("capability") != WAKE_CAPABILITY:
            continue
        if delivery.get("dispatch_performed") is not True:
            continue
        if not delivery.get("task_id") or not delivery.get("wake_attempt_id"):
            continue

        reconcile_id = str(delivery.get("reconcile_id") or "").strip()
        if not reconcile_id or path.stem != reconcile_id:
            continue
        try:
            record = _read(intents / f"{reconcile_id}.json")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not record or record.get("schema") != INTENT_RECORD_SCHEMA:
            continue
        if record.get("reconcile_id") != reconcile_id or record.get("state") != "planned":
            continue
        if record.get("dispatch_performed") is not False:
            continue
        intent = record.get("intent")
        if not isinstance(intent, dict) or intent.get("schema") != RECONCILE_INTENT_SCHEMA:
            continue
        if intent.get("kind") != "employee_wake":
            continue
        if intent.get("employee_id") != delivery.get("employee_id"):
            continue
        if intent.get("assignment_id") != delivery.get("assignment_id"):
            continue
        if intent.get("authority_boundary") != "observe_and_select_only":
            continue
        if any(
            intent.get(key) != "unbound"
            for key in ("node_selection", "executor_selection", "transport_selection", "capability_authority")
        ):
            continue
        if intent.get("credential_exposed") is not False:
            continue
        wake = intent.get("wake_intent")
        if not isinstance(wake, dict):
            continue

        key = _delivery_index_key(
            employee_id=delivery.get("employee_id"),
            assignment_id=delivery.get("assignment_id"),
            wake_id=delivery.get("wake_id"),
            node_id=delivery.get("node_id"),
            presence_id=delivery.get("presence_id"),
            presence_generation=delivery.get("presence_generation"),
            wake=wake,
        )
        index.setdefault(key, []).append(delivery)

    _GOVERNED_DELIVERY_INDEX_CACHE[cache_key] = (signature, index)
    return index


def require_governed_product_delivery(
    runtime_root: str | Path,
    runner_kind: str,
    capsule: dict[str, Any],
) -> dict[str, Any]:
    """Bind one product wake to one exact Supervisor/S4 delivery before claim.

    Historical Supervisor evidence is indexed per directory generation so a
    steady-state worker performs an O(1) exact lookup instead of rescanning every
    reconcile JSON on every poll. Atomic evidence replacement changes directory
    metadata and invalidates the cache.
    """
    _require_runner_scope(runner_kind, capsule, runtime_root=runtime_root)
    root = Path(runtime_root).expanduser().resolve()
    wake = capsule.get("wake_intent")
    key = _delivery_index_key(
        employee_id=capsule.get("employee_id"),
        assignment_id=capsule.get("assignment_id"),
        wake_id=capsule.get("wake_id"),
        node_id=capsule.get("node_id"),
        presence_id=capsule.get("presence_id"),
        presence_generation=capsule.get("presence_generation"),
        wake=wake,
    )
    matches = _governed_delivery_index(root).get(key, [])

    if len(matches) != 1:
        raise PermissionError(
            "product_employee_worker_governed_delivery_ambiguous"
            if len(matches) > 1
            else "product_employee_worker_governed_delivery_missing"
        )
    return matches[0]


@dataclass(slots=True)
class ProductWorkerState:
    status: str
    runner_kind: str
    employee_id: str
    assignment_id: str
    wake_id: str
    presence_generation: int
    lease_generation: int
    thread_head: str
    error_code: str | None = None
    executor_provider: str = "unbound"
    executor_model: str = ""


class GovernedProductEmployeeWorker:
    """Credential-isolated product Employee worker behind the governed wake boundary.

    Product v1 is intentionally bounded. Zeus may consume a content-addressed
    work-intent and execute only the fixed read-only review adapter. YouTube has no
    governed live read adapter in this runner yet. A bounded run must therefore end
    in a durable terminal handoff/blocker receipt rather than leaving an active lease
    to expire into an infinite UNKNOWN/resume loop. Product repository writes,
    publication, external API mutation, credentials, network and arbitrary executable
    selection remain outside this worker's authority.
    """

    def __init__(
        self,
        *,
        runtime_root: str | Path,
        wake_root: str | Path,
        worker_state_root: str | Path,
        node_id: str,
        runner_kind: str,
        lease_seconds: int = 60,
    ) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.wake_root = Path(wake_root).expanduser().resolve()
        self.worker_state_root = Path(worker_state_root).expanduser().resolve()
        self.node_id = str(node_id or "").strip()
        self.runner_kind = str(runner_kind or "").strip()
        self.lease_seconds = int(lease_seconds)
        if self.runner_kind not in SUPPORTED_PRODUCT_RUNNERS:
            raise ValueError("product_employee_runner_kind_not_allowed")
        if not self.node_id:
            raise ValueError("product_employee_node_id_required")

    def _execute_zeus_review(
        self,
        work_ref: dict[str, Any],
        *,
        employee_id: str,
        wake_id: str,
        presence_generation: int,
    ) -> dict[str, Any]:
        receipt = execute_bound_work_intent(work_ref)
        receipt_path = (
            self.worker_state_root
            / "product-receipts"
            / employee_id
            / f"{wake_id}.p{presence_generation:06d}.json"
        )
        _atomic_write(receipt_path, receipt)
        return receipt

    def _capsules(self) -> list[tuple[Path, dict[str, Any]]]:
        scope = SUPPORTED_PRODUCT_RUNNERS[self.runner_kind]
        root = self.wake_root / scope["employee_id"]
        result: list[tuple[Path, dict[str, Any]]] = []
        if not root.is_dir():
            return result
        for path in sorted(root.glob("*.json")):
            try:
                payload = _read(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not payload or payload.get("node_id") != self.node_id:
                continue
            try:
                _require_runner_scope(self.runner_kind, payload, runtime_root=self.runtime_root)
            except PermissionError:
                continue
            result.append((path, payload))
        return result

    def process_exact(self, *, wake_id: str, presence_generation: int) -> ProductWorkerState | None:
        wake = str(wake_id or "").strip()
        generation = int(presence_generation)
        matches = [
            item
            for item in self._capsules()
            if str(item[1].get("wake_id") or "") == wake
            and int(item[1].get("presence_generation") or 0) == generation
        ]
        if len(matches) > 1:
            raise RuntimeError("product_employee_worker_exact_wake_ambiguous")
        if not matches:
            return None
        _, capsule = matches[0]
        require_governed_product_delivery(self.runtime_root, self.runner_kind, capsule)

        runtime = EmployeeRuntime(self.runtime_root)
        lifecycle = EmployeeLifecycle(runtime)
        employee_id = str(capsule["employee_id"])
        assignment_id = str(capsule["assignment_id"])
        # Hydrate before claiming the durable lease; invalid root/skill fails closed.
        source_root = Path(__file__).resolve().parents[1]
        roles = RoleRegistry(source_root / ".agent/roles/registry.yaml")
        skills = EmployeeSkillRegistry(source_root / "governance/employee-skills.json")
        employee = runtime.get_employee(employee_id)
        expected_scope = SUPPORTED_PRODUCT_RUNNERS[self.runner_kind]
        if set(employee.role_ids) != expected_scope["role_ids"] or set(employee.skill_ids) != expected_scope["skill_ids"]:
            raise PermissionError("product_employee_runtime_role_skill_mismatch")
        effective = roles.hydrate_employee_roles(employee.role_ids)
        if any(role.protocols.get("pdca") != "root.pdca.v1" for role in effective):
            raise PermissionError("product_employee_root_pdca_not_hydrated")
        EmployeeSkillService(runtime, roles, skills).hydrate_employee_skills(employee_id)
        lease_id = f"product-{self.runner_kind}-{wake}-{generation}"
        lease = lifecycle.claim(
            assignment_id,
            employee_id,
            lease_id,
            lease_seconds=self.lease_seconds,
        )
        expected = int(capsule.get("expected_lease_generation") or 0)
        if lease.generation != expected:
            return ProductWorkerState(
                status="unknown",
                runner_kind=self.runner_kind,
                employee_id=employee_id,
                assignment_id=assignment_id,
                wake_id=wake,
                presence_generation=generation,
                lease_generation=lease.generation,
                thread_head=lease.thread_head,
                error_code="product_employee_worker_lease_generation_mismatch",
            )

        if self.runner_kind == "paw_inspect_v1":
            # Separately owned engineering authority directory; never derive
            # execution authority, a file path or key from the wake capsule.
            authority_dir = self.worker_state_root / "trusted-engineering-authority"
            from agentos_node.paw_engineering_request import trusted_request_filename
            request_file = authority_dir / trusted_request_filename(assignment_id)
            public_file = authority_dir / "paw-470-issuer.pub"
            _await_paw_request_after_claim(request_file, public_file)
            if request_file.exists() != public_file.exists():
                raise PermissionError("paw_engineering_authority_incomplete")
            if request_file.is_file() and public_file.is_file():
                import stat
                from agentos_node.paw_engineering_public_signature import verify_paw_public_signature
                from agentos_node.paw_engineering_executor import run_authorized_static_candidate
                from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError

                def trusted_regular(path: Path) -> bool:
                    meta = path.lstat()
                    return (
                        stat.S_ISREG(meta.st_mode)
                        and meta.st_uid == os.geteuid()
                        and not (meta.st_mode & 0o077)
                        and meta.st_nlink == 1
                    )

                if not all(
                    (path.exists() and not path.is_symlink() and trusted_regular(path))
                    for path in (request_file, public_file)
                ):
                    raise PawWorktreeBoundaryError("paw_issuer_file_not_trusted")
                public_key = public_file.read_bytes()
                if request_file.stat().st_size > 65536:
                    raise PawWorktreeBoundaryError("paw_signed_request_too_large")
                signed = verify_paw_public_signature(json.loads(request_file.read_text(encoding="utf-8")), public_key=public_key)
                git_root = source_root
                isolated_root = self.worker_state_root / "paw-470-worktrees"
                # The signed request is checked before any git mutation.
                isolated_root.mkdir(mode=0o700, parents=True, exist_ok=True)
                commit = run_authorized_static_candidate(
                    grant_payload=signed["grant"],
                    expected_sha256=signed["expected_sha256"],
                    replacement=signed["replacement"],
                    trusted_wake_id=wake,
                    trusted_presence_generation=generation,
                    trusted_lease_generation=lease.generation,
                    trusted_lease_id=lease_id,
                    lifecycle=lifecycle,
                    registry_path=source_root / "governance/execution-authority.json",
                    trusted_assignment_id=assignment_id,
                    trusted_runtime=runtime,
                    repository=git_root,
                    workspace_root=isolated_root,
                )
                from agentos_node.paw_engineering_bundle import export_paw_bundle
                bundle_path = export_paw_bundle(
                    worktree=isolated_root / commit.work_id,
                    destination=self.worker_state_root / "paw-470-bundles" / (commit.work_id + ".bundle"),
                    work_id=commit.work_id, commit_sha=commit.commit_sha,
                )
                thread_head = "paw:local-commit:" + commit.commit_sha
                lifecycle.checkpoint(assignment_id, lease_id, thread_head)
                lifecycle.finish(
                    assignment_id, lease_id, state="handoff",
                    result_summary={
                        "bounded_stage": "paw-authorized-local-commit",
                        "work_id": commit.work_id,
                        "base_sha": commit.base_sha,
                        "commit_sha": commit.commit_sha,
                        "bundle_path": str(bundle_path),
                        "branch": commit.branch,
                        "changed_file": commit.changed_file,
                        "published": False,
                        "independent_acceptance_pass": False,
                        "mutation_performed": True,
                        "credential_exposed": False,
                    },
                )
                employee = runtime.get_employee(employee_id)
                return ProductWorkerState(
                    status="handoff", runner_kind=self.runner_kind,
                    employee_id=employee_id, assignment_id=assignment_id,
                    wake_id=wake, presence_generation=generation,
                    lease_generation=lease.generation, thread_head=thread_head,
                    executor_provider=employee.executor.provider,
                    executor_model=employee.executor.model,
                )
            # Paw can do a real, fixed-scope inspection without engineering write
            # authority. This is a diagnostic, never independent Claw PASS.
            observation = inspect_completion_470(
                canonical_executor_job_request("completion.470.status.inspect")
            )
            observed = observation.get("verdict") == "PASS"
            blocker = (
                "paw_engineering_execution_not_authorized"
                if observed else "paw_completion_470_inspector_unavailable"
            )
            thread_head = f"paw:inspect:{blocker}:{wake}:p{generation}:l{lease.generation}"
            lease = lifecycle.checkpoint(assignment_id, lease_id, thread_head)
            lifecycle.finish(
                assignment_id, lease_id, state="blocked",
                result_summary={
                    "bounded_stage": "completion-470-readonly-inspection",
                    "blocker_code": blocker,
                    "inspection_verdict": observation.get("verdict"),
                    "inspection_classification": observation.get("classification"),
                    "inspected_work_id": observation.get("work_id") if observed else None,
                    "inspected_status": observation.get("completion_status") if observed else None,
                    "inspected_retry_count": observation.get("completion_machine_retry_count") if observed else None,
                    "mutation_performed": False, "independent_acceptance_pass": False,
                    "credential_exposed": False,
                },
            )
            employee = runtime.get_employee(employee_id)
            return ProductWorkerState(
                status="blocked", runner_kind=self.runner_kind, employee_id=employee_id,
                assignment_id=assignment_id, wake_id=wake, presence_generation=generation,
                lease_generation=lease.generation, thread_head=lease.thread_head,
                error_code=blocker, executor_provider=employee.executor.provider,
                executor_model=employee.executor.model,
            )

        if self.runner_kind == "youtube_ai_manager_scan_v1":
            blocker = "youtube_governed_read_adapter_unavailable"
            thread_head = (
                f"product-worker:{self.runner_kind}:blocked:{blocker}:"
                f"{wake}:p{generation}:l{lease.generation}"
            )
            lease = lifecycle.checkpoint(assignment_id, lease_id, thread_head)
            lifecycle.finish(
                assignment_id,
                lease_id,
                state="blocked",
                result_summary={
                    "bounded_stage": "youtube-read-only-scan",
                    "blocker_code": blocker,
                    "external_api_read_performed": False,
                    "external_api_mutation_performed": False,
                    "credential_exposed": False,
                },
            )
            employee = runtime.get_employee(employee_id)
            return ProductWorkerState(
                status="blocked",
                runner_kind=self.runner_kind,
                employee_id=employee_id,
                assignment_id=assignment_id,
                wake_id=wake,
                presence_generation=generation,
                lease_generation=lease.generation,
                thread_head=lease.thread_head,
                error_code=blocker,
                executor_provider=employee.executor.provider,
                executor_model=employee.executor.model,
            )

        wake_intent = capsule.get("wake_intent") or {}
        work_ref = wake_intent.get("work_intent_ref")
        if work_ref is None:
            blocker = "zeus_product_work_intent_missing"
            thread_head = (
                f"product-worker:{self.runner_kind}:blocked:{blocker}:"
                f"{wake}:p{generation}:l{lease.generation}"
            )
            lease = lifecycle.checkpoint(assignment_id, lease_id, thread_head)
            lifecycle.finish(
                assignment_id,
                lease_id,
                state="blocked",
                result_summary={
                    "bounded_stage": "zeus-existing-draft-review",
                    "blocker_code": blocker,
                    "mutation_performed": False,
                    "publish_performed": False,
                    "credential_exposed": False,
                },
            )
            employee = runtime.get_employee(employee_id)
            return ProductWorkerState(
                status="blocked",
                runner_kind=self.runner_kind,
                employee_id=employee_id,
                assignment_id=assignment_id,
                wake_id=wake,
                presence_generation=generation,
                lease_generation=lease.generation,
                thread_head=lease.thread_head,
                error_code=blocker,
                executor_provider=employee.executor.provider,
                executor_model=employee.executor.model,
            )

        receipt = self._execute_zeus_review(
            work_ref,
            employee_id=employee_id,
            wake_id=wake,
            presence_generation=generation,
        )
        evidence = receipt.get("evidence") if isinstance(receipt, dict) else None
        evidence = evidence if isinstance(evidence, dict) else {}
        result_status = str(receipt.get("result_status") or "") if isinstance(receipt, dict) else ""
        chapter = str(evidence.get("chapter") or "").strip()
        digest = str(evidence.get("work_intent_digest") or "").removeprefix("sha256:")
        safe_review = bool(
            result_status == "success"
            and chapter
            and len(digest) == 64
            and evidence.get("mutation_performed") is False
            and evidence.get("publish_performed") is False
            and receipt.get("credential_exposed") is False
        )
        if not safe_review:
            blocker = str(
                receipt.get("error_code")
                if isinstance(receipt, dict) and receipt.get("error_code")
                else "zeus_product_review_receipt_invalid"
            )[:160]
            thread_head = (
                f"product-worker:{self.runner_kind}:blocked:{blocker}:"
                f"{wake}:p{generation}:l{lease.generation}"
            )
            lease = lifecycle.checkpoint(assignment_id, lease_id, thread_head)
            lifecycle.finish(
                assignment_id,
                lease_id,
                state="blocked",
                result_summary={
                    "bounded_stage": "zeus-existing-draft-review",
                    "blocker_code": blocker,
                    "mutation_performed": False,
                    "publish_performed": False,
                    "credential_exposed": False,
                },
            )
            employee = runtime.get_employee(employee_id)
            return ProductWorkerState(
                status="blocked",
                runner_kind=self.runner_kind,
                employee_id=employee_id,
                assignment_id=assignment_id,
                wake_id=wake,
                presence_generation=generation,
                lease_generation=lease.generation,
                thread_head=lease.thread_head,
                error_code=blocker,
                executor_provider=employee.executor.provider,
                executor_model=employee.executor.model,
            )

        thread_head = (
            f"product-worker:{self.runner_kind}:review-existing-draft:"
            f"{chapter}:{digest[:16]}:{wake}:p{generation}:l{lease.generation}"
        )
        lease = lifecycle.checkpoint(assignment_id, lease_id, thread_head)
        lifecycle.finish(
            assignment_id,
            lease_id,
            state="handoff",
            result_summary={
                "bounded_stage": "zeus-existing-draft-review",
                "chapter": chapter,
                "work_intent_digest": "sha256:" + digest,
                "mutation_performed": False,
                "publish_performed": False,
                "next_authority_required": "zeus-product-draft-mutation",
                "credential_exposed": False,
            },
        )
        employee = runtime.get_employee(employee_id)
        return ProductWorkerState(
            status="handoff",
            runner_kind=self.runner_kind,
            employee_id=employee_id,
            assignment_id=assignment_id,
            wake_id=wake,
            presence_generation=generation,
            lease_generation=lease.generation,
            thread_head=lease.thread_head,
            executor_provider=employee.executor.provider,
            executor_model=employee.executor.model,
        )

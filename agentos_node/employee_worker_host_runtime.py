from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agentos_node.employee_worker_host import (
    SAFE_CHILD_RESULT_KEYS,
    EmployeeWorkerAdapter,
    EmployeeWorkerHost,
    WorkerHostCandidate,
)


ROOT = Path(__file__).resolve().parent.parent
V2_ADAPTER_REGISTRY = ROOT / "governance" / "employee-worker-adapters-v2.json"
V2_REGISTRY_SCHEMA = "agentos.employee-worker-adapters/v2"
V2_RUNNER_KINDS = {
    "spec_steward_o3",
    "zeus_writer_v1",
    "youtube_ai_manager_scan_v1",
}
V2_RESULT_SCHEMAS = {
    "spec_steward_o3": "agentos.spec-steward-o3-worker-cli-result/v1",
    "zeus_writer_v1": "agentos.zeus-writer-worker-cli-result/v1",
    "youtube_ai_manager_scan_v1": "agentos.youtube-ai-manager-scan-worker-cli-result/v1",
}


class ProductEmployeeWorkerAdapterRegistry:
    """V2 source-controlled registry for fixed bounded Employee runner kinds."""

    def __init__(self, path: str | Path = V2_ADAPTER_REGISTRY) -> None:
        self.path = Path(path).expanduser().resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != V2_REGISTRY_SCHEMA:
            raise ValueError("employee_worker_adapter_v2_registry_schema_invalid")
        raw = payload.get("adapters")
        if not isinstance(raw, list) or not raw:
            raise ValueError("employee_worker_adapter_v2_registry_entries_invalid")

        self._adapters: list[EmployeeWorkerAdapter] = []
        seen_ids: set[str] = set()
        seen_scopes: set[tuple[str, str]] = set()
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError("employee_worker_adapter_v2_shape_invalid")
            runner_kind = str(entry.get("runner_kind") or "").strip()
            adapter_id = str(entry.get("adapter_id") or "").strip()
            employee_id = str(entry.get("employee_id") or "").strip()
            assignment_id = str(entry.get("assignment_id") or "").strip()
            status = str(entry.get("status") or "").strip().lower()
            role_ids = tuple(str(value).strip() for value in (entry.get("role_ids") or []))
            skill_ids = tuple(str(value).strip() for value in (entry.get("skill_ids") or []))
            if runner_kind not in V2_RUNNER_KINDS:
                raise ValueError("employee_worker_adapter_v2_runner_kind_invalid")
            if status not in {"active", "disabled"}:
                raise ValueError("employee_worker_adapter_v2_status_invalid")
            if not adapter_id or not employee_id or not assignment_id or not all(role_ids) or not all(skill_ids):
                raise ValueError("employee_worker_adapter_v2_scope_invalid")
            if adapter_id in seen_ids or (employee_id, assignment_id) in seen_scopes:
                raise ValueError("employee_worker_adapter_v2_duplicate")
            seen_ids.add(adapter_id)
            seen_scopes.add((employee_id, assignment_id))
            self._adapters.append(
                EmployeeWorkerAdapter(
                    adapter_id=adapter_id,
                    status=status,
                    runner_kind=runner_kind,
                    employee_id=employee_id,
                    assignment_id=assignment_id,
                    role_ids=role_ids,
                    skill_ids=skill_ids,
                )
            )

    def resolve(self, capsule: dict[str, Any]) -> EmployeeWorkerAdapter | None:
        intent = capsule.get("wake_intent")
        if not isinstance(intent, dict):
            return None
        employee_id = str(capsule.get("employee_id") or "").strip()
        assignment_id = str(capsule.get("assignment_id") or "").strip()
        role_ids = set(str(value).strip() for value in (intent.get("role_ids") or []))
        skill_ids = set(str(value).strip() for value in (intent.get("skill_ids") or []))
        matches = [
            adapter
            for adapter in self._adapters
            if adapter.status == "active"
            and adapter.employee_id == employee_id
            and adapter.assignment_id == assignment_id
            and set(adapter.role_ids) == role_ids
            and set(adapter.skill_ids) == skill_ids
        ]
        if len(matches) > 1:
            raise RuntimeError("employee_worker_adapter_v2_resolution_ambiguous")
        return matches[0] if matches else None

    def projection(self) -> list[dict[str, Any]]:
        return [
            {
                "adapter_id": item.adapter_id,
                "status": item.status,
                "runner_kind": item.runner_kind,
                "employee_id": item.employee_id,
                "assignment_id": item.assignment_id,
                "role_ids": list(item.role_ids),
                "skill_ids": list(item.skill_ids),
            }
            for item in self._adapters
        ]


class ExactEmployeeWorkerHost(EmployeeWorkerHost):
    """One shared credential-isolated host for exact fixed Employee runner kinds.

    The underlying EmployeeWorkerHost still owns the durable dispatch ledger,
    crash/UNKNOWN semantics and allowlisted child environment. This wrapper only
    expands source-controlled runner selection and pins one exact wake per launch.
    """

    def __init__(self, **kwargs: Any) -> None:
        # Base initialization intentionally uses the existing v1 Spec Steward registry
        # so all original validation and host setup remain unchanged. Runtime selection
        # is then replaced with the stricter v2 fixed-runner registry.
        super().__init__(**kwargs)
        self.registry = ProductEmployeeWorkerAdapterRegistry()
        self._pinned_candidate: WorkerHostCandidate | None = None

    def _candidates(self) -> list[WorkerHostCandidate]:
        if self._pinned_candidate is not None:
            return [self._pinned_candidate]
        candidates = super()._candidates()
        if candidates:
            self._pinned_candidate = candidates[0]
        return candidates

    def _child_command(self, adapter: EmployeeWorkerAdapter) -> list[str]:
        candidate = self._pinned_candidate
        if candidate is None:
            raise RuntimeError("employee_worker_exact_candidate_missing")
        if adapter.runner_kind == "spec_steward_o3":
            command = EmployeeWorkerHost._child_command(self, adapter)
        elif adapter.runner_kind in {"zeus_writer_v1", "youtube_ai_manager_scan_v1"}:
            command = [
                sys.executable,
                "-m",
                "agentos_node.product_employee_worker_cli",
                "--runner-kind",
                adapter.runner_kind,
                "--runtime-root",
                str(self.runtime_root),
                "--wake-root",
                str(self.wake_root),
                "--worker-state-root",
                str(self.worker_state_root),
                "--node-id",
                self.node_id,
                "--lease-seconds",
                str(self.lease_seconds),
                "--once",
            ]
        else:
            raise RuntimeError("employee_worker_runner_kind_unimplemented")
        command.extend(
            [
                "--wake-id",
                str(candidate.capsule["wake_id"]),
                "--presence-generation",
                str(candidate.capsule["presence_generation"]),
            ]
        )
        return command

    def _parse_child_result(self, stdout: str) -> dict[str, Any] | None:
        candidate = self._pinned_candidate
        if candidate is None:
            return None
        lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
        if not lines:
            return None
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or set(payload) - SAFE_CHILD_RESULT_KEYS:
            return None
        if payload.get("schema") != V2_RESULT_SCHEMAS.get(candidate.adapter.runner_kind):
            return None
        if payload.get("credential_exposed") is not False:
            return None
        if payload.get("session_identity_exposed") is not False:
            return None
        if payload.get("verified_marker_emitted") is not False:
            return None
        return payload

    def process_one(self) -> dict[str, Any] | None:
        self._pinned_candidate = None
        try:
            return super().process_one()
        finally:
            self._pinned_candidate = None

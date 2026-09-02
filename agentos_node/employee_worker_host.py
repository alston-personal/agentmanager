from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ADAPTER_REGISTRY = ROOT / "governance" / "employee-worker-adapters.json"
REGISTRY_SCHEMA = "agentos.employee-worker-adapters/v1"
WAKE_CAPSULE_SCHEMA = "agentos.employee-wake-delivery/v1"
DISPATCH_SCHEMA = "agentos.employee-worker-host-dispatch/v1"
ADAPTER_FIELDS = {
    "adapter_id",
    "status",
    "runner_kind",
    "employee_id",
    "assignment_id",
    "role_ids",
    "skill_ids",
}
REGISTRY_FIELDS = {"schema", "adapters"}
CAPSULE_FIELDS = {
    "schema",
    "wake_id",
    "employee_id",
    "assignment_id",
    "node_id",
    "presence_id",
    "presence_generation",
    "expected_lease_generation",
    "digest",
    "wake_intent",
    "employee_wake_route",
}
ACTIVE_RUNNER_KINDS = {"spec_steward_o3"}
TERMINAL_DISPATCH_STATES = {"checkpointed", "completed", "failed", "unknown", "rejected"}
SAFE_CHILD_RESULT_KEYS = {
    "schema",
    "status",
    "work_performed",
    "employee_id",
    "assignment_id",
    "wake_id",
    "presence_generation",
    "lease_generation",
    "thread_head",
    "error_code",
    "executor_provider",
    "executor_model",
    "credential_exposed",
    "session_identity_exposed",
    "verified_marker_emitted",
}
CHILD_RESULT_SCHEMA = "agentos.spec-steward-o3-worker-cli-result/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 256 or text in {".", ".."} or any(ch in text for ch in "/\\\0"):
        raise ValueError(f"invalid_employee_worker_{field}")
    return text


def _absolute(value: str | Path, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"employee_worker_{field}_must_be_absolute")
    return path.resolve()


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 64:
        raise ValueError(f"invalid_employee_worker_{field}")
    result = tuple(_safe_id(item, field) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"duplicate_employee_worker_{field}")
    return result


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


@dataclass(frozen=True, slots=True)
class EmployeeWorkerAdapter:
    adapter_id: str
    status: str
    runner_kind: str
    employee_id: str
    assignment_id: str
    role_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]


class EmployeeWorkerAdapterRegistry:
    """Source-controlled adapter registry; never carries executable/module/argv authority."""

    def __init__(self, path: str | Path = DEFAULT_ADAPTER_REGISTRY) -> None:
        self.path = Path(path).expanduser().resolve()
        self._adapters = self._load()

    def _load(self) -> tuple[EmployeeWorkerAdapter, ...]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != REGISTRY_FIELDS:
            raise ValueError("employee_worker_adapter_registry_shape_invalid")
        if payload.get("schema") != REGISTRY_SCHEMA:
            raise ValueError("employee_worker_adapter_registry_schema_invalid")
        raw_adapters = payload.get("adapters")
        if not isinstance(raw_adapters, list) or not raw_adapters or len(raw_adapters) > 128:
            raise ValueError("employee_worker_adapter_registry_entries_invalid")

        adapters: list[EmployeeWorkerAdapter] = []
        ids: set[str] = set()
        scopes: set[tuple[str, str]] = set()
        for raw in raw_adapters:
            if not isinstance(raw, dict) or set(raw) != ADAPTER_FIELDS:
                raise ValueError("employee_worker_adapter_shape_invalid")
            adapter_id = _safe_id(raw.get("adapter_id"), "adapter_id")
            status = str(raw.get("status") or "").strip().lower()
            runner_kind = str(raw.get("runner_kind") or "").strip()
            employee_id = _safe_id(raw.get("employee_id"), "employee_id")
            assignment_id = _safe_id(raw.get("assignment_id"), "assignment_id")
            if status not in {"active", "disabled"}:
                raise ValueError("employee_worker_adapter_status_invalid")
            if runner_kind not in ACTIVE_RUNNER_KINDS:
                raise ValueError("employee_worker_adapter_runner_kind_invalid")
            if adapter_id in ids or (employee_id, assignment_id) in scopes:
                raise ValueError("employee_worker_adapter_duplicate")
            ids.add(adapter_id)
            scopes.add((employee_id, assignment_id))
            adapters.append(
                EmployeeWorkerAdapter(
                    adapter_id=adapter_id,
                    status=status,
                    runner_kind=runner_kind,
                    employee_id=employee_id,
                    assignment_id=assignment_id,
                    role_ids=_string_list(raw.get("role_ids"), "role_ids"),
                    skill_ids=_string_list(raw.get("skill_ids"), "skill_ids"),
                )
            )
        return tuple(adapters)

    def resolve(self, capsule: dict[str, Any]) -> EmployeeWorkerAdapter | None:
        intent = capsule.get("wake_intent")
        if not isinstance(intent, dict):
            return None
        try:
            employee_id = _safe_id(capsule.get("employee_id"), "employee_id")
            assignment_id = _safe_id(capsule.get("assignment_id"), "assignment_id")
            role_ids = _string_list(intent.get("role_ids"), "role_ids")
            skill_ids = _string_list(intent.get("skill_ids"), "skill_ids")
        except ValueError:
            return None
        matches = [
            adapter
            for adapter in self._adapters
            if adapter.status == "active"
            and adapter.employee_id == employee_id
            and adapter.assignment_id == assignment_id
            and set(adapter.role_ids) == set(role_ids)
            and set(adapter.skill_ids) == set(skill_ids)
        ]
        if len(matches) > 1:
            raise RuntimeError("employee_worker_adapter_resolution_ambiguous")
        return matches[0] if matches else None

    def projection(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self._adapters]


@dataclass(frozen=True, slots=True)
class WorkerHostCandidate:
    path: Path
    capsule: dict[str, Any]
    adapter: EmployeeWorkerAdapter


class EmployeeWorkerHost:
    """Credential-isolated Node host for source-registered bounded Employee adapters.

    The host never decides Employee claim authority. A child adapter must re-check
    the canonical Supervisor/S4 evidence before claiming an assignment.
    """

    def __init__(
        self,
        *,
        runtime_root: str | Path,
        wake_root: str | Path,
        host_state_root: str | Path,
        worker_state_root: str | Path,
        node_id: str,
        adapter_registry_path: str | Path = DEFAULT_ADAPTER_REGISTRY,
        child_timeout_seconds: int = 180,
        lease_seconds: int = 60,
    ) -> None:
        self.runtime_root = _absolute(runtime_root, "runtime_root")
        self.wake_root = _absolute(wake_root, "wake_root")
        self.host_state_root = _absolute(host_state_root, "host_state_root")
        self.worker_state_root = _absolute(worker_state_root, "worker_state_root")
        self.node_id = _safe_id(node_id, "node_id")
        self.registry = EmployeeWorkerAdapterRegistry(adapter_registry_path)
        self.child_timeout_seconds = int(child_timeout_seconds)
        self.lease_seconds = int(lease_seconds)
        if self.child_timeout_seconds < 5 or self.child_timeout_seconds > 1800:
            raise ValueError("employee_worker_child_timeout_invalid")
        if self.lease_seconds < 30 or self.lease_seconds > 3600:
            raise ValueError("employee_worker_lease_seconds_invalid")

    @property
    def dispatch_root(self) -> Path:
        return self.host_state_root / "dispatches"

    def _read_capsule(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or set(payload) != CAPSULE_FIELDS:
            return None
        if payload.get("schema") != WAKE_CAPSULE_SCHEMA:
            return None
        try:
            employee_id = _safe_id(payload.get("employee_id"), "employee_id")
            _safe_id(payload.get("assignment_id"), "assignment_id")
            _safe_id(payload.get("wake_id"), "wake_id")
            _safe_id(payload.get("presence_id"), "presence_id")
            node_id = _safe_id(payload.get("node_id"), "node_id")
        except ValueError:
            return None
        if path.parent.name != employee_id or node_id != self.node_id:
            return None
        presence_generation = payload.get("presence_generation")
        lease_generation = payload.get("expected_lease_generation")
        if (
            isinstance(presence_generation, bool)
            or not isinstance(presence_generation, int)
            or presence_generation < 1
            or isinstance(lease_generation, bool)
            or not isinstance(lease_generation, int)
            or lease_generation < 1
        ):
            return None
        return payload

    def _dispatch_path(self, capsule: dict[str, Any]) -> Path:
        employee_id = _safe_id(capsule.get("employee_id"), "employee_id")
        wake_id = _safe_id(capsule.get("wake_id"), "wake_id")
        generation = int(capsule.get("presence_generation") or 0)
        return self.dispatch_root / employee_id / f"{wake_id}.{generation:06d}.json"

    def _read_dispatch(self, capsule: dict[str, Any]) -> dict[str, Any] | None:
        path = self._dispatch_path(capsule)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("employee_worker_dispatch_state_invalid") from exc
        if not isinstance(payload, dict) or payload.get("schema") != DISPATCH_SCHEMA:
            raise RuntimeError("employee_worker_dispatch_state_invalid")
        return payload

    def _candidates(self) -> list[WorkerHostCandidate]:
        if not self.wake_root.is_dir():
            return []
        result: list[WorkerHostCandidate] = []
        for path in self.wake_root.glob("*/*.json"):
            capsule = self._read_capsule(path)
            if capsule is None:
                continue
            adapter = self.registry.resolve(capsule)
            if adapter is None:
                continue
            existing = self._read_dispatch(capsule)
            if existing and existing.get("status") in TERMINAL_DISPATCH_STATES:
                continue
            result.append(WorkerHostCandidate(path=path, capsule=capsule, adapter=adapter))
        result.sort(
            key=lambda item: (
                int(item.capsule.get("expected_lease_generation") or 0),
                int(item.capsule.get("presence_generation") or 0),
                item.path.name,
            )
        )
        return result

    def _dispatch_id(self, candidate: WorkerHostCandidate) -> str:
        capsule = candidate.capsule
        material = "|".join(
            [
                candidate.adapter.adapter_id,
                self.node_id,
                str(capsule.get("wake_id") or ""),
                str(capsule.get("presence_generation") or ""),
            ]
        )
        return "worker-dispatch-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

    def _new_dispatch(self, candidate: WorkerHostCandidate) -> dict[str, Any]:
        capsule = candidate.capsule
        return {
            "schema": DISPATCH_SCHEMA,
            "dispatch_id": self._dispatch_id(candidate),
            "adapter_id": candidate.adapter.adapter_id,
            "runner_kind": candidate.adapter.runner_kind,
            "employee_id": capsule["employee_id"],
            "assignment_id": capsule["assignment_id"],
            "wake_id": capsule["wake_id"],
            "node_id": capsule["node_id"],
            "presence_id": capsule["presence_id"],
            "presence_generation": capsule["presence_generation"],
            "expected_lease_generation": capsule["expected_lease_generation"],
            "status": "launching",
            "started_at": _utc_now(),
            "completed_at": None,
            "error_code": None,
            "child_result": None,
            "credential_exposed": False,
            "session_identity_exposed": False,
        }

    def _persist_dispatch(self, candidate: WorkerHostCandidate, state: dict[str, Any]) -> dict[str, Any]:
        _atomic_write(self._dispatch_path(candidate.capsule), state)
        return state

    def _child_command(self, adapter: EmployeeWorkerAdapter) -> list[str]:
        if adapter.runner_kind != "spec_steward_o3":
            raise RuntimeError("employee_worker_runner_kind_unimplemented")
        return [
            sys.executable,
            "-m",
            "agentos_node.spec_steward_worker_cli",
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

    @staticmethod
    def _child_environment() -> dict[str, str]:
        env: dict[str, str] = {
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
            "PATH": os.path.dirname(sys.executable) or os.defpath,
        }
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    @staticmethod
    def _parse_child_result(stdout: str) -> dict[str, Any] | None:
        lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
        if not lines:
            return None
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or set(payload) - SAFE_CHILD_RESULT_KEYS:
            return None
        if payload.get("schema") != CHILD_RESULT_SCHEMA:
            return None
        if payload.get("credential_exposed") is not False:
            return None
        if payload.get("session_identity_exposed") is not False:
            return None
        if payload.get("verified_marker_emitted") is not False:
            return None
        return payload

    @staticmethod
    def _safe_child_projection(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: payload.get(key) for key in sorted(SAFE_CHILD_RESULT_KEYS) if key in payload}

    def _reconcile_child_result(
        self,
        candidate: WorkerHostCandidate,
        state: dict[str, Any],
        *,
        returncode: int,
        stdout: str,
    ) -> dict[str, Any]:
        child = self._parse_child_result(stdout)
        if child is None:
            state["status"] = "unknown"
            state["error_code"] = "employee_worker_child_result_untrusted"
        else:
            exact = (
                child.get("employee_id") == candidate.capsule.get("employee_id")
                and child.get("assignment_id") == candidate.capsule.get("assignment_id")
                and child.get("wake_id") == candidate.capsule.get("wake_id")
                and int(child.get("presence_generation") or 0)
                == int(candidate.capsule.get("presence_generation") or 0)
            )
            status = str(child.get("status") or "")
            expected_generation = int(candidate.capsule.get("expected_lease_generation") or 0)
            lease_generation = int(child.get("lease_generation") or 0)
            if not exact:
                state["status"] = "unknown"
                state["error_code"] = "employee_worker_child_wake_mismatch"
            elif status in {"checkpointed", "completed"} and returncode == 0 and lease_generation == expected_generation:
                state["status"] = status
                state["error_code"] = None
            elif status == "failed":
                state["status"] = "failed"
                state["error_code"] = str(child.get("error_code") or "employee_worker_child_failed")[:160]
            else:
                state["status"] = "unknown"
                state["error_code"] = (
                    str(child.get("error_code") or "employee_worker_child_execution_uncertain")[:160]
                )
            state["child_result"] = self._safe_child_projection(child)
        state["completed_at"] = _utc_now()
        return self._persist_dispatch(candidate, state)

    def process_one(self) -> dict[str, Any] | None:
        candidates = self._candidates()
        if not candidates:
            return None
        candidate = candidates[0]
        existing = self._read_dispatch(candidate.capsule)
        if existing is not None:
            # A prior host process crossed the launch boundary and disappeared.
            # The child may have changed Employee state, so never replay blindly.
            if existing.get("status") == "launching":
                existing["status"] = "unknown"
                existing["error_code"] = "employee_worker_prior_launch_unknown"
                existing["completed_at"] = _utc_now()
                return self._persist_dispatch(candidate, existing)
            return None

        state = self._new_dispatch(candidate)
        self._persist_dispatch(candidate, state)
        try:
            completed = subprocess.run(
                self._child_command(candidate.adapter),
                cwd=str(ROOT),
                env=self._child_environment(),
                text=True,
                capture_output=True,
                timeout=self.child_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            state["status"] = "unknown"
            state["error_code"] = "employee_worker_child_execution_uncertain"
            state["completed_at"] = _utc_now()
            return self._persist_dispatch(candidate, state)
        return self._reconcile_child_result(
            candidate,
            state,
            returncode=int(completed.returncode),
            stdout=completed.stdout,
        )

    def status(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        if self.dispatch_root.is_dir():
            for path in self.dispatch_root.glob("*/*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    counts["invalid"] = counts.get("invalid", 0) + 1
                    continue
                status = str(payload.get("status") or "invalid") if isinstance(payload, dict) else "invalid"
                counts[status] = counts.get(status, 0) + 1
        return {
            "schema": "agentos.employee-worker-host-status/v1",
            "node_id": self.node_id,
            "adapter_count": len([a for a in self.registry.projection() if a.get("status") == "active"]),
            "dispatch_counts": dict(sorted(counts.items())),
            "credential_exposed": False,
            "session_identity_exposed": False,
        }

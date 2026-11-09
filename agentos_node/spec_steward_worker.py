from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_memory import EmployeeMemoryPolicy, EmployeeMemoryService
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_skills import EmployeeSkillRegistry, EmployeeSkillService
from agent_core.employee_wake import EmployeeWakeIntent, EmployeeWakePlanner, WAKE_INTENT_SCHEMA
from agent_core.role_runtime import RoleRegistry
from agent_core.spec_steward_acceptance import (
    DEFAULT_MEMORY_POLICY_PATH,
    LIVE_WITNESS_SCHEMA,
    MEMORY_CLASS,
    MEMORY_EVIDENCE_SCHEMA,
    MEMORY_KEY,
    inspect_spec_steward_acceptance,
)
from agent_core.spec_steward_bootstrap import (
    DEFAULT_ROLE_REGISTRY_PATH,
    DEFAULT_SKILL_REGISTRY_PATH,
    build_spec_steward_audit_request,
    load_spec_steward_contract,
)
from agentos_node.employee_wake_inbox import (
    ALLOWED_INTENT_KEYS,
    ROUTE_KEYS,
    WAKE_RECEIPT_SCHEMA,
    WAKE_ROUTE_SCHEMA,
)


WORKER_STATE_SCHEMA = "agentos.spec-steward-o3-worker-state/v1"
CONTINUITY_SCHEMA = "agentos.spec-steward-o3-worker-continuity/v1"
EMPLOYEE_ID = "agentos-spec-steward"
ASSIGNMENT_ID = "spec-steward-o3-acceptance-v1"
SKILL_ID = "spec.audit"
EXECUTOR_PROVIDER = "agentos-native-spec-audit"
EXECUTOR_MODEL = "spec-audit-v1"
CAPSULE_KEYS = {
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
TERMINAL_LOCAL_STATES = {"checkpointed", "completed", "unknown", "failed"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 256 or any(ch in text for ch in "/\\\0") or text in {".", ".."}:
        raise ValueError(f"invalid_spec_steward_worker_{field}")
    return text


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("spec_steward_worker_state_invalid")
    return payload


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_separate_roots(runtime_root: Path, wake_root: Path, state_root: Path) -> None:
    roots = [runtime_root.resolve(), wake_root.resolve(), state_root.resolve()]
    if len(set(roots)) != 3:
        raise ValueError("spec_steward_worker_roots_must_be_distinct")
    if _inside(wake_root.resolve(), runtime_root.resolve()) or _inside(runtime_root.resolve(), wake_root.resolve()):
        raise ValueError("spec_steward_worker_wake_root_must_not_be_canonical_runtime")
    if _inside(state_root.resolve(), runtime_root.resolve()) or _inside(runtime_root.resolve(), state_root.resolve()):
        raise ValueError("spec_steward_worker_state_root_must_not_be_canonical_runtime")


def _capsule_digest(intent: dict[str, Any], route: dict[str, Any]) -> str:
    raw = json.dumps(
        {"wake_intent": intent, "employee_wake_route": route},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _instance_digest(instance_id: str) -> str:
    return hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:24]


def _lease_id(wake_id: str, presence_generation: int, digest: str) -> str:
    raw = f"{wake_id}\0{presence_generation}\0{digest}".encode("utf-8")
    return "employeelease_" + hashlib.sha256(raw).hexdigest()[:24]


def _thread_head(generation: int, audit: dict[str, Any]) -> str:
    raw = json.dumps(audit, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"o3:checkpoint:g{int(generation)}:{hashlib.sha256(raw).hexdigest()[:16]}"


@dataclass(slots=True)
class SpecStewardWorkerState:
    schema: str
    wake_id: str
    digest: str
    employee_id: str
    assignment_id: str
    node_id: str
    presence_id: str
    presence_generation: int
    expected_lease_generation: int
    lease_id: str
    lease_generation: int | None
    status: str
    process_instance_digest: str
    executor_provider: str
    executor_model: str
    created_at: str
    updated_at: str
    thread_head: str = ""
    error_code: str | None = None
    credential_exposed: bool = False
    session_identity_exposed: bool = False
    verified_marker_emitted: bool = False


class NativeSpecStewardAuditExecutor:
    """Fixed read-only O3 audit executor.

    It does not run shell, select a provider, call a network endpoint, or mutate the
    target project. It audits the already-persisted O3 acceptance evidence and
    returns bounded closure-gap data for the Employee lifecycle to checkpoint.
    """

    provider = EXECUTOR_PROVIDER
    model = EXECUTOR_MODEL
    skill_id = SKILL_ID

    def execute(
        self,
        runtime: EmployeeRuntime,
        *,
        skill_request: dict[str, Any],
        lease_generation: int,
    ) -> tuple[str, dict[str, Any]]:
        if skill_request.get("intent") != "audit":
            raise PermissionError("spec_steward_worker_intent_not_audit")
        if (skill_request.get("skill") or {}).get("skill_id") != SKILL_ID:
            raise PermissionError("spec_steward_worker_skill_mismatch")
        if skill_request.get("capability_authorization") != "required_downstream":
            raise PermissionError("spec_steward_worker_skill_authority_boundary_invalid")
        if skill_request.get("credential_exposed") is not False:
            raise PermissionError("spec_steward_worker_skill_credential_boundary_invalid")
        args = skill_request.get("args") or {}
        if args.get("scope") != "core-issue-197-o3":
            raise PermissionError("spec_steward_worker_scope_mismatch")

        report = inspect_spec_steward_acceptance(runtime)
        audit = {
            "schema": "agentos.spec-steward-o3-native-audit/v1",
            "scope": "core-issue-197-o3",
            "lease_generation": int(lease_generation),
            "blocking_count": len(report.blocking_reasons),
            "blocking_checks": list(report.blocking_reasons),
            "qualifying_wake_generations": list(report.qualifying_wake_generations),
            "credential_exposed": False,
            "session_identity_exposed": False,
        }
        return _thread_head(lease_generation, audit), audit


class SpecStewardWakeWorker:
    """Consume exact Spec Steward wake capsules without turning wake into authority.

    The wake inbox remains delivery-only. This worker is a separately configured,
    fixed Employee/skill executor. It requires an already-materialized canonical
    EmployeeRuntime and never creates an Employee or assignment. The first O3 lease
    intentionally stops after checkpoint; only a later wake generation may resume
    and finish, which lets the live acceptance prove process/executor continuity.
    """

    def __init__(
        self,
        *,
        runtime_root: str | Path,
        wake_root: str | Path,
        worker_state_root: str | Path,
        node_id: str,
        process_instance_id: str | None = None,
        lease_seconds: int = 60,
        executor: NativeSpecStewardAuditExecutor | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.wake_root = Path(wake_root).expanduser().resolve()
        self.worker_state_root = Path(worker_state_root).expanduser().resolve()
        _require_separate_roots(self.runtime_root, self.wake_root, self.worker_state_root)
        self.node_id = _safe_id(node_id, "node_id")
        if lease_seconds < 30 or lease_seconds > 3600:
            raise ValueError("spec_steward_worker_lease_seconds_out_of_range")
        self.lease_seconds = int(lease_seconds)
        self.process_instance_digest = _instance_digest(process_instance_id or uuid.uuid4().hex)
        self.executor = executor or NativeSpecStewardAuditExecutor()
        if self.executor.provider != EXECUTOR_PROVIDER or self.executor.skill_id != SKILL_ID:
            raise ValueError("spec_steward_worker_executor_contract_mismatch")

        # Fail before creating local worker state if the caller points at an empty
        # or competing runtime. Bootstrap must already have materialized canonical
        # Employee state through Core.
        if not (self.runtime_root / "employees" / f"{EMPLOYEE_ID}.json").is_file():
            raise RuntimeError("spec_steward_worker_canonical_employee_missing")
        if not (self.runtime_root / "assignments" / f"{ASSIGNMENT_ID}.json").is_file():
            raise RuntimeError("spec_steward_worker_canonical_assignment_missing")

        self.runtime = EmployeeRuntime(self.runtime_root)
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.role_registry = RoleRegistry(DEFAULT_ROLE_REGISTRY_PATH)
        self.skill_registry = EmployeeSkillRegistry(DEFAULT_SKILL_REGISTRY_PATH)
        self.skill_service = EmployeeSkillService(self.runtime, self.role_registry, self.skill_registry)
        self.memory = EmployeeMemoryService(
            self.runtime,
            self.role_registry,
            EmployeeMemoryPolicy(DEFAULT_MEMORY_POLICY_PATH),
        )
        self.contract = load_spec_steward_contract()
        self.state_dir = self.worker_state_root / EMPLOYEE_ID

    def _state_path(self, wake_id: str, presence_generation: int) -> Path:
        return self.state_dir / f"{_safe_id(wake_id, 'wake_id')}.{int(presence_generation):06d}.json"

    def _load_state(self, wake_id: str, presence_generation: int) -> SpecStewardWorkerState | None:
        payload = _read(self._state_path(wake_id, presence_generation))
        if payload is None:
            return None
        if payload.get("schema") != WORKER_STATE_SCHEMA:
            raise ValueError("spec_steward_worker_state_schema_invalid")
        return SpecStewardWorkerState(**payload)

    def _persist(self, state: SpecStewardWorkerState) -> SpecStewardWorkerState:
        _atomic(self._state_path(state.wake_id, state.presence_generation), asdict(state))
        return state

    def _capsules(self) -> list[tuple[int, Path, dict[str, Any]]]:
        employee_dir = self.wake_root / EMPLOYEE_ID
        if not employee_dir.is_dir():
            return []
        candidates: list[tuple[int, Path, dict[str, Any]]] = []
        for path in sorted(employee_dir.glob("*.json")):
            try:
                payload = _read(path)
                if not payload or payload.get("schema") != WAKE_RECEIPT_SCHEMA:
                    continue
                generation = int(payload.get("expected_lease_generation") or 0)
                if generation < 1:
                    continue
                state = self._load_state(
                    str(payload.get("wake_id") or ""),
                    int(payload.get("presence_generation") or 0),
                )
                if state is not None and state.status in TERMINAL_LOCAL_STATES:
                    continue
                candidates.append((generation, path, payload))
            except Exception:
                continue
        candidates.sort(key=lambda item: (item[0], item[1].name))
        return candidates

    def _validate_capsule(self, capsule: dict[str, Any], *, now: datetime) -> EmployeeWakeIntent:
        if set(capsule) != CAPSULE_KEYS:
            raise ValueError("spec_steward_worker_capsule_fields_invalid")
        if capsule.get("schema") != WAKE_RECEIPT_SCHEMA:
            raise ValueError("spec_steward_worker_capsule_schema_invalid")
        if capsule.get("employee_id") != EMPLOYEE_ID or capsule.get("assignment_id") != ASSIGNMENT_ID:
            raise PermissionError("spec_steward_worker_capsule_scope_mismatch")
        if capsule.get("node_id") != self.node_id:
            raise PermissionError("spec_steward_worker_node_mismatch")
        presence_generation = int(capsule.get("presence_generation") or 0)
        if presence_generation < 1:
            raise ValueError("spec_steward_worker_presence_generation_invalid")

        intent = capsule.get("wake_intent")
        route = capsule.get("employee_wake_route")
        if not isinstance(intent, dict) or set(intent) != ALLOWED_INTENT_KEYS:
            raise ValueError("spec_steward_worker_wake_intent_invalid")
        if not isinstance(route, dict) or set(route) != ROUTE_KEYS:
            raise ValueError("spec_steward_worker_wake_route_invalid")
        if intent.get("schema") != WAKE_INTENT_SCHEMA or route.get("schema") != WAKE_ROUTE_SCHEMA:
            raise ValueError("spec_steward_worker_wake_schema_invalid")
        if intent.get("employee_id") != EMPLOYEE_ID or intent.get("assignment_id") != ASSIGNMENT_ID:
            raise PermissionError("spec_steward_worker_wake_scope_mismatch")
        if route.get("employee_id") != EMPLOYEE_ID or route.get("node_id") != self.node_id:
            raise PermissionError("spec_steward_worker_route_scope_mismatch")
        if route.get("presence_id") != capsule.get("presence_id"):
            raise ValueError("spec_steward_worker_presence_id_mismatch")
        if int(route.get("presence_generation") or 0) != presence_generation:
            raise ValueError("spec_steward_worker_presence_generation_mismatch")
        if intent.get("wake_id") != capsule.get("wake_id"):
            raise ValueError("spec_steward_worker_wake_id_mismatch")
        if int(intent.get("expected_lease_generation") or 0) != int(capsule.get("expected_lease_generation") or 0):
            raise ValueError("spec_steward_worker_lease_generation_mismatch")
        if intent.get("authority_boundary") != "selection_only_no_execution":
            raise PermissionError("spec_steward_worker_wake_authority_boundary_invalid")
        if intent.get("executor_selection") != "unbound" or intent.get("transport_selection") != "unbound":
            raise PermissionError("spec_steward_worker_wake_prebound_execution_rejected")
        if intent.get("credential_exposed") is not False:
            raise PermissionError("spec_steward_worker_wake_credential_boundary_invalid")
        if intent.get("role_ids") != ["governance.spec_steward"] or intent.get("skill_ids") != [SKILL_ID]:
            raise PermissionError("spec_steward_worker_role_skill_scope_mismatch")
        if intent.get("mode") not in {"fresh", "resume"}:
            raise ValueError("spec_steward_worker_wake_mode_invalid")

        digest = _capsule_digest(intent, route)
        if capsule.get("digest") != digest:
            raise ValueError("spec_steward_worker_capsule_digest_mismatch")

        employee = self.runtime.get_employee(EMPLOYEE_ID)
        assignment = self.runtime.get_assignment(ASSIGNMENT_ID)
        if employee.role_ids != ["governance.spec_steward"] or employee.skill_ids != [SKILL_ID]:
            raise PermissionError("spec_steward_worker_employee_contract_drift")
        if assignment.employee_id != EMPLOYEE_ID:
            raise PermissionError("spec_steward_worker_assignment_employee_mismatch")

        wake = EmployeeWakeIntent(
            schema=WAKE_INTENT_SCHEMA,
            wake_id=str(intent["wake_id"]),
            employee_id=EMPLOYEE_ID,
            assignment_id=ASSIGNMENT_ID,
            mode=str(intent["mode"]),
            expected_lease_generation=int(intent["expected_lease_generation"]),
            goal=str(intent["goal"]),
            thread_head=str(intent["thread_head"]),
            constraints=tuple(str(item) for item in intent["constraints"]),
            role_ids=("governance.spec_steward",),
            skill_ids=(SKILL_ID,),
            resume_required=intent.get("resume_required") is True,
            prior_execution_state=str(intent["prior_execution_state"]),
        )
        current = EmployeeWakePlanner(self.lifecycle).plan_next(EMPLOYEE_ID, now=now)
        if current is None or current.as_dict() != wake.as_dict():
            raise RuntimeError("spec_steward_worker_wake_no_longer_current")
        return wake

    def _initial_state(self, capsule: dict[str, Any], *, now: datetime) -> SpecStewardWorkerState:
        wake_id = str(capsule["wake_id"])
        presence_generation = int(capsule["presence_generation"])
        return SpecStewardWorkerState(
            schema=WORKER_STATE_SCHEMA,
            wake_id=wake_id,
            digest=str(capsule["digest"]),
            employee_id=EMPLOYEE_ID,
            assignment_id=ASSIGNMENT_ID,
            node_id=self.node_id,
            presence_id=str(capsule["presence_id"]),
            presence_generation=presence_generation,
            expected_lease_generation=int(capsule["expected_lease_generation"]),
            lease_id=_lease_id(wake_id, presence_generation, str(capsule["digest"])),
            lease_generation=None,
            status="accepted",
            process_instance_digest=self.process_instance_digest,
            executor_provider=self.executor.provider,
            executor_model=self.executor.model,
            created_at=_iso(now),
            updated_at=_iso(now),
        )

    def _previous_checkpoint_state(self, generation: int, thread_head: str) -> SpecStewardWorkerState | None:
        if generation <= 1 or not self.state_dir.is_dir():
            return None
        candidates: list[SpecStewardWorkerState] = []
        for path in self.state_dir.glob("*.json"):
            try:
                payload = _read(path)
                if not payload or payload.get("schema") != WORKER_STATE_SCHEMA:
                    continue
                state = SpecStewardWorkerState(**payload)
            except Exception:
                continue
            if (
                state.lease_generation == generation - 1
                and state.status == "checkpointed"
                and state.thread_head == thread_head
            ):
                candidates.append(state)
        candidates.sort(key=lambda item: (item.updated_at, item.wake_id), reverse=True)
        return candidates[0] if candidates else None

    def _write_generation_continuity(self, generation: int, thread_head: str) -> None:
        self.memory.write(
            EMPLOYEE_ID,
            "continuity",
            f"spec-steward-o3-generation-{int(generation)}",
            {
                "schema": CONTINUITY_SCHEMA,
                "employee_id": EMPLOYEE_ID,
                "assignment_id": ASSIGNMENT_ID,
                "lease_generation": int(generation),
                "thread_head": thread_head,
                "credential_exposed": False,
                "session_identity_exposed": False,
            },
        )

    def _prior_continuity_ok(self, generation: int, thread_head: str) -> bool:
        if generation <= 1:
            return False
        try:
            payload = self.memory.read(
                EMPLOYEE_ID,
                "continuity",
                f"spec-steward-o3-generation-{int(generation) - 1}",
            )
        except (FileNotFoundError, PermissionError, ValueError):
            return False
        return bool(
            isinstance(payload, dict)
            and payload.get("schema") == CONTINUITY_SCHEMA
            and payload.get("employee_id") == EMPLOYEE_ID
            and payload.get("assignment_id") == ASSIGNMENT_ID
            and int(payload.get("lease_generation") or 0) == generation - 1
            and payload.get("thread_head") == thread_head
            and payload.get("credential_exposed") is False
            and payload.get("session_identity_exposed") is False
        )

    def _write_live_witness(self, state: SpecStewardWorkerState, lease: Any, previous: SpecStewardWorkerState, *, now: datetime) -> bool:
        if previous.process_instance_digest == self.process_instance_digest:
            return False
        if lease.resumed_from_lease_id != previous.lease_id:
            return False
        if previous.lease_generation != lease.generation - 1:
            return False
        _atomic(
            self.runtime_root / "acceptance" / "spec-steward-o3-live-witness.json",
            {
                "schema": LIVE_WITNESS_SCHEMA,
                "employee_id": EMPLOYEE_ID,
                "assignment_id": ASSIGNMENT_ID,
                "witness_kind": "fresh_executor_or_session_transition",
                "from_lease_id": previous.lease_id,
                "to_lease_id": state.lease_id,
                "from_generation": previous.lease_generation,
                "to_generation": lease.generation,
                "fresh_executor_or_session": True,
                "process_boundary_observed": True,
                "session_identity_exposed": False,
                "credential_exposed": False,
                "observed_at": _iso(now),
            },
        )
        return True

    def process_one(self, *, now: datetime | None = None) -> SpecStewardWorkerState | None:
        current_time = now or _utcnow()
        candidates = self._capsules()
        if not candidates:
            return None
        _, _, capsule = candidates[0]
        wake_id = str(capsule.get("wake_id") or "")
        presence_generation = int(capsule.get("presence_generation") or 0)
        state = self._load_state(wake_id, presence_generation)
        if state is not None and state.status == "executing":
            state.status = "unknown"
            state.error_code = "worker_interrupted_after_execution_boundary"
            state.updated_at = _iso(current_time)
            return self._persist(state)
        if state is not None and state.status in TERMINAL_LOCAL_STATES:
            return state

        try:
            wake = self._validate_capsule(capsule, now=current_time)
            if state is None:
                state = self._persist(self._initial_state(capsule, now=current_time))

            self.skill_service.hydrate_employee_skills(EMPLOYEE_ID)
            skill_request = build_spec_steward_audit_request(self.runtime)
            if skill_request.get("execution_authority") != "external_governed_dispatcher":
                raise PermissionError("spec_steward_worker_skill_execution_boundary_invalid")

            self.runtime.bind_executor(
                EMPLOYEE_ID,
                provider=self.executor.provider,
                model=self.executor.model,
                session_id="",
            )
            lease = self.lifecycle.claim(
                ASSIGNMENT_ID,
                EMPLOYEE_ID,
                state.lease_id,
                lease_seconds=self.lease_seconds,
                now=current_time,
            )
            if lease.generation != wake.expected_lease_generation:
                raise RuntimeError("spec_steward_worker_claim_generation_mismatch")
            if wake.mode == "resume" and not lease.resume_required:
                raise RuntimeError("spec_steward_worker_resume_lease_not_marked")
            if wake.mode == "fresh" and lease.resume_required:
                raise RuntimeError("spec_steward_worker_fresh_lease_marked_resume")
            state.lease_generation = lease.generation
            state.status = "leased"
            state.process_instance_digest = self.process_instance_digest
            state.updated_at = _iso(current_time)
            self._persist(state)

            self.lifecycle.build_work_packet(
                ASSIGNMENT_ID,
                state.lease_id,
                self.role_registry,
                now=current_time,
            )
            previous = self._previous_checkpoint_state(lease.generation, wake.thread_head)
            prior_memory_ok = self._prior_continuity_ok(lease.generation, wake.thread_head)

            state.status = "executing"
            state.updated_at = _iso(current_time)
            self._persist(state)
            thread_head, audit = self.executor.execute(
                self.runtime,
                skill_request=skill_request,
                lease_generation=lease.generation,
            )
            self.lifecycle.checkpoint(
                ASSIGNMENT_ID,
                state.lease_id,
                thread_head,
                now=current_time,
            )
            state.thread_head = thread_head
            self._write_generation_continuity(lease.generation, thread_head)

            if wake.mode == "fresh":
                # O3 intentionally requires a later process/executor transition.
                # Do not finish generation 1; the lease must expire and be resumed.
                state.status = "checkpointed"
                state.error_code = None
                state.updated_at = _iso(current_time)
                return self._persist(state)

            if previous is None or not prior_memory_ok:
                raise RuntimeError("spec_steward_worker_resume_continuity_evidence_missing")
            self._write_live_witness(state, lease, previous, now=current_time)
            self.memory.write(
                EMPLOYEE_ID,
                MEMORY_CLASS,
                MEMORY_KEY,
                {
                    "schema": MEMORY_EVIDENCE_SCHEMA,
                    "employee_id": EMPLOYEE_ID,
                    "assignment_id": ASSIGNMENT_ID,
                    "thread_head": thread_head,
                    "observed_after_resume": True,
                    "session_identity_exposed": False,
                    "credential_exposed": False,
                },
            )

            preterminal = inspect_spec_steward_acceptance(self.runtime)
            receipt = self.lifecycle.finish(
                ASSIGNMENT_ID,
                state.lease_id,
                result_summary={
                    "acceptance_scope": "core-issue-197-o3",
                    "audit_blocking_count_before_terminal": len(preterminal.blocking_reasons),
                    "audit_blocking_checks_before_terminal": list(preterminal.blocking_reasons),
                    "native_audit_blocking_count": int(audit.get("blocking_count") or 0),
                    "credential_exposed": False,
                    "session_identity_exposed": False,
                },
                now=current_time,
            )
            if receipt.credential_exposed is not False:
                raise RuntimeError("spec_steward_worker_terminal_receipt_privacy_invalid")
            final_report = inspect_spec_steward_acceptance(self.runtime)
            state.status = "completed"
            state.error_code = None if final_report.ready_for_live_marker else "o3_acceptance_evidence_incomplete"
            state.updated_at = _iso(current_time)
            return self._persist(state)
        except Exception:
            if state is None:
                state = self._initial_state(capsule, now=current_time)
            state.status = "unknown" if state.status == "executing" else "failed"
            state.error_code = (
                "worker_execution_uncertain" if state.status == "unknown" else "worker_pre_execution_failed"
            )
            state.updated_at = _iso(current_time)
            return self._persist(state)

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.core_work_items import WorkItemStore
from agent_core.employee_lifecycle import EmployeeLifecycle, RECEIPT_SCHEMA
from agent_core.employee_memory import EmployeeMemoryPolicy, EmployeeMemoryService
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_skills import EmployeeSkillRegistry, EmployeeSkillService
from agent_core.role_runtime import RoleRegistry
from agent_core.spec_steward_bootstrap import (
    DEFAULT_ROLE_REGISTRY_PATH,
    DEFAULT_SKILL_REGISTRY_PATH,
    SpecStewardBootstrapContract,
    load_spec_steward_contract,
)


REPORT_SCHEMA = "agentos.spec-steward-o3-acceptance-report/v1"
LIVE_WITNESS_SCHEMA = "agentos.spec-steward-o3-live-witness/v1"
MEMORY_EVIDENCE_SCHEMA = "agentos.spec-steward-o3-memory-evidence/v1"
DEFAULT_MEMORY_POLICY_PATH = (
    Path(__file__).resolve().parent.parent / "governance" / "employee-memory-policy.json"
)
MEMORY_CLASS = "governance_evidence"
MEMORY_KEY = "spec-steward-o3-continuity"
EXPECTED_AUTHORITY_POLICY = "core-supervisor-employee-wake-v1"
EXPECTED_TRANSPORT = "one_direct"
LIVE_WITNESS_FIELDS = {
    "schema",
    "employee_id",
    "assignment_id",
    "witness_kind",
    "from_lease_id",
    "to_lease_id",
    "from_generation",
    "to_generation",
    "fresh_executor_or_session",
    "process_boundary_observed",
    "session_identity_exposed",
    "credential_exposed",
    "observed_at",
}
MEMORY_EVIDENCE_FIELDS = {
    "schema",
    "employee_id",
    "assignment_id",
    "thread_head",
    "observed_after_resume",
    "session_identity_exposed",
    "credential_exposed",
}
RECEIPT_FORBIDDEN_KEYS = {
    "session",
    "session_id",
    "credential",
    "credentials",
    "token",
    "secret",
    "authorization",
    "password",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
}
SECRET_MARKERS = (
    "bearer ",
    "github_pat_",
    "ghp_",
    "token=",
    "secret=",
    "authorization:",
    "session_id=",
)


@dataclass(frozen=True, slots=True)
class SpecStewardAcceptanceReport:
    schema: str
    employee_id: str
    assignment_id: str
    checks: dict[str, bool]
    blocking_reasons: tuple[str, ...]
    qualifying_delivery_count: int
    qualifying_wake_generations: tuple[int, ...]
    observed_lease_generation: int | None
    terminal_receipt_generation: int | None
    ready_for_live_marker: bool
    live_attestation_required: bool = True
    verified_marker_emitted: bool = False
    credential_exposed: bool = False
    session_identity_exposed: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["blocking_reasons"] = list(self.blocking_reasons)
        value["qualifying_wake_generations"] = list(self.qualifying_wake_generations)
        return value


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("spec_steward_acceptance_evidence_invalid")
    return payload


def _exact_fields(payload: dict[str, Any], expected: set[str]) -> bool:
    return set(payload) == expected


def _safe_receipt_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        lowered = value.casefold()
        return not any(marker in lowered for marker in SECRET_MARKERS)
    if isinstance(value, list):
        return all(_safe_receipt_value(item) for item in value)
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().casefold()
            if key in RECEIPT_FORBIDDEN_KEYS:
                return False
            if not _safe_receipt_value(item):
                return False
        return True
    return False


def _employee_contract_ok(runtime: EmployeeRuntime, contract: SpecStewardBootstrapContract) -> bool:
    try:
        employee = runtime.get_employee(contract.employee.employee_id)
    except (FileNotFoundError, ValueError):
        return False
    return bool(
        employee.agent_id == contract.employee.employee_id
        and employee.display_name == contract.employee.display_name
        and tuple(employee.role_ids) == contract.employee.role_ids
        and tuple(employee.skill_ids) == contract.employee.skill_ids
        and employee.memory_namespace == f"employee:{contract.employee.employee_id}"
    )


def _machine_contracts_ok(
    runtime: EmployeeRuntime,
    contract: SpecStewardBootstrapContract,
    role_registry: RoleRegistry,
    skill_registry: EmployeeSkillRegistry,
) -> bool:
    try:
        employee = runtime.get_employee(contract.employee.employee_id)
        roles = role_registry.hydrate_employee_roles(list(employee.role_ids))
        skills = EmployeeSkillService(runtime, role_registry, skill_registry).hydrate_employee_skills(
            employee.agent_id
        )
    except (FileNotFoundError, KeyError, PermissionError, ValueError):
        return False
    role_capabilities = {
        capability
        for role in roles
        for capability in role.capabilities
    }
    return bool(
        tuple(skill.skill_id for skill in skills) == contract.employee.skill_ids
        and set(contract.initial_work_item.required_capabilities).issubset(role_capabilities)
    )


def _work_item_ok(runtime: EmployeeRuntime, contract: SpecStewardBootstrapContract) -> bool:
    try:
        persisted = WorkItemStore(runtime).get(contract.initial_work_item.work_item_id)
    except (FileNotFoundError, ValueError):
        return False
    return persisted == contract.initial_work_item


def _assignment_ok(runtime: EmployeeRuntime, contract: SpecStewardBootstrapContract) -> bool:
    try:
        assignment = runtime.get_assignment(contract.initial_work_item.assignment_id)
    except (FileNotFoundError, ValueError):
        return False
    return bool(
        assignment.employee_id == contract.employee.employee_id
        and assignment.goal == contract.initial_work_item.goal
        and tuple(assignment.constraints) == contract.initial_work_item.constraints
    )


def _qualifying_deliveries(runtime: EmployeeRuntime, contract: SpecStewardBootstrapContract) -> list[dict[str, Any]]:
    root = runtime.root / "supervisor" / "deliveries"
    if not root.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not payload or payload.get("schema") != DELIVERY_STATE_SCHEMA:
            continue
        if payload.get("employee_id") != contract.employee.employee_id:
            continue
        if payload.get("assignment_id") != contract.initial_work_item.assignment_id:
            continue
        if payload.get("transport") != EXPECTED_TRANSPORT:
            continue
        if payload.get("authority_policy_id") != EXPECTED_AUTHORITY_POLICY:
            continue
        if payload.get("capability") != WAKE_CAPABILITY:
            continue
        if payload.get("dispatch_performed") is not True:
            continue
        if payload.get("status") not in {"claimed", "terminal_observed"}:
            continue
        if not payload.get("task_id") or not payload.get("node_id") or not payload.get("presence_id"):
            continue
        if int(payload.get("presence_generation") or 0) < 1:
            continue
        result.append(payload)
    return result


def _qualifying_wake_generations(
    runtime: EmployeeRuntime,
    contract: SpecStewardBootstrapContract,
    deliveries: list[dict[str, Any]],
) -> tuple[int, ...]:
    generations: set[int] = set()
    intents_root = runtime.root / "supervisor" / "intents"
    for delivery in deliveries:
        reconcile_id = str(delivery.get("reconcile_id") or "").strip()
        if not reconcile_id:
            continue
        try:
            record = _read_json(intents_root / f"{reconcile_id}.json")
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
        if intent.get("employee_id") != contract.employee.employee_id:
            continue
        if intent.get("assignment_id") != contract.initial_work_item.assignment_id:
            continue
        wake = intent.get("wake_intent")
        if not isinstance(wake, dict):
            continue
        if wake.get("wake_id") != delivery.get("wake_id"):
            continue
        if wake.get("employee_id") != contract.employee.employee_id:
            continue
        if wake.get("assignment_id") != contract.initial_work_item.assignment_id:
            continue
        if wake.get("credential_exposed") is not False:
            continue
        generation = int(wake.get("expected_lease_generation") or 0)
        if generation >= 1:
            generations.add(generation)
    return tuple(sorted(generations))


def _memory_continuity_ok(
    runtime: EmployeeRuntime,
    contract: SpecStewardBootstrapContract,
    assignment_thread_head: str,
    *,
    role_registry: RoleRegistry,
    memory_policy_path: str | Path,
) -> bool:
    service = EmployeeMemoryService(
        runtime,
        role_registry,
        EmployeeMemoryPolicy(memory_policy_path),
    )
    try:
        payload = service.read(contract.employee.employee_id, MEMORY_CLASS, MEMORY_KEY)
    except (FileNotFoundError, PermissionError, ValueError):
        return False
    if not isinstance(payload, dict) or not _exact_fields(payload, MEMORY_EVIDENCE_FIELDS):
        return False
    return bool(
        payload.get("schema") == MEMORY_EVIDENCE_SCHEMA
        and payload.get("employee_id") == contract.employee.employee_id
        and payload.get("assignment_id") == contract.initial_work_item.assignment_id
        and payload.get("thread_head") == assignment_thread_head
        and payload.get("observed_after_resume") is True
        and payload.get("session_identity_exposed") is False
        and payload.get("credential_exposed") is False
    )


def _live_witness_ok(
    runtime: EmployeeRuntime,
    contract: SpecStewardBootstrapContract,
    *,
    current_lease: Any,
) -> bool:
    path = runtime.root / "acceptance" / "spec-steward-o3-live-witness.json"
    try:
        payload = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not payload or not _exact_fields(payload, LIVE_WITNESS_FIELDS):
        return False
    if current_lease is None:
        return False
    return bool(
        payload.get("schema") == LIVE_WITNESS_SCHEMA
        and payload.get("employee_id") == contract.employee.employee_id
        and payload.get("assignment_id") == contract.initial_work_item.assignment_id
        and payload.get("witness_kind") == "fresh_executor_or_session_transition"
        and payload.get("from_lease_id") == current_lease.resumed_from_lease_id
        and payload.get("to_lease_id") == current_lease.lease_id
        and int(payload.get("from_generation") or 0) == current_lease.generation - 1
        and int(payload.get("to_generation") or 0) == current_lease.generation
        and payload.get("fresh_executor_or_session") is True
        and payload.get("process_boundary_observed") is True
        and payload.get("session_identity_exposed") is False
        and payload.get("credential_exposed") is False
        and bool(str(payload.get("observed_at") or "").strip())
    )


def _terminal_receipt(
    runtime: EmployeeRuntime,
    contract: SpecStewardBootstrapContract,
    *,
    current_lease: Any,
    assignment_thread_head: str,
) -> tuple[bool, int | None]:
    if current_lease is None:
        return False, None
    path = (
        runtime.root
        / "lifecycle"
        / "receipts"
        / contract.initial_work_item.assignment_id
        / f"{int(current_lease.generation):06d}.json"
    )
    try:
        payload = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False, None
    if not payload:
        return False, None
    result_summary = payload.get("result_summary")
    ok = bool(
        payload.get("schema") == RECEIPT_SCHEMA
        and payload.get("employee_id") == contract.employee.employee_id
        and payload.get("assignment_id") == contract.initial_work_item.assignment_id
        and payload.get("lease_id") == current_lease.lease_id
        and int(payload.get("generation") or 0) == current_lease.generation
        and payload.get("outcome") == "completed"
        and payload.get("thread_head") == assignment_thread_head
        and payload.get("credential_exposed") is False
        and isinstance(result_summary, dict)
        and _safe_receipt_value(result_summary)
    )
    return ok, int(payload.get("generation") or 0) if ok else None


def inspect_spec_steward_acceptance(
    runtime: EmployeeRuntime,
    *,
    contract_path: str | Path | None = None,
    role_registry_path: str | Path = DEFAULT_ROLE_REGISTRY_PATH,
    skill_registry_path: str | Path = DEFAULT_SKILL_REGISTRY_PATH,
    memory_policy_path: str | Path = DEFAULT_MEMORY_POLICY_PATH,
) -> SpecStewardAcceptanceReport:
    """Read O3 evidence without mutating Employee, Supervisor, ONE, or acceptance state.

    A complete report only means persisted evidence is ready for a separate live
    attestation step. This inspector never emits the O3 VERIFIED marker, including
    when exercised by static CI.
    """
    contract = load_spec_steward_contract(contract_path) if contract_path else load_spec_steward_contract()
    role_registry = RoleRegistry(role_registry_path)
    skill_registry = EmployeeSkillRegistry(skill_registry_path)
    lifecycle = EmployeeLifecycle(runtime)

    checks: dict[str, bool] = {}
    checks["employee_contract"] = _employee_contract_ok(runtime, contract)
    checks["active_role_and_skill_hydrated"] = _machine_contracts_ok(
        runtime, contract, role_registry, skill_registry
    )
    checks["canonical_work_item"] = _work_item_ok(runtime, contract)
    checks["assignment_contract"] = _assignment_ok(runtime, contract)

    try:
        assignment = runtime.get_assignment(contract.initial_work_item.assignment_id)
    except (FileNotFoundError, ValueError):
        assignment = None
    assignment_thread_head = assignment.thread_head if assignment else ""
    checks["checkpoint_thread_head"] = bool(
        assignment
        and assignment_thread_head
        and assignment_thread_head != contract.initial_thread_head
    )

    deliveries = _qualifying_deliveries(runtime, contract)
    wake_generations = _qualifying_wake_generations(runtime, contract, deliveries)
    checks["governed_one_wake_delivery"] = bool(deliveries)

    try:
        lease = lifecycle.get_lease(contract.initial_work_item.assignment_id)
    except (ValueError, TypeError):
        lease = None
    checks["resumed_assignment_lease"] = bool(
        lease
        and lease.generation >= 2
        and lease.resume_required is True
        and lease.prior_execution_state == "unknown"
        and bool(lease.resumed_from_lease_id)
        and lease.resumed_from_lease_id != lease.lease_id
        and lease.thread_head == assignment_thread_head
        and assignment_thread_head != contract.initial_thread_head
    )
    checks["initial_and_resume_wakes_governed"] = bool(
        lease
        and 1 in wake_generations
        and int(lease.generation) in wake_generations
    )
    checks["fresh_executor_or_session_live_witness"] = _live_witness_ok(
        runtime, contract, current_lease=lease
    )
    checks["private_memory_continuity"] = bool(
        assignment_thread_head
        and _memory_continuity_ok(
            runtime,
            contract,
            assignment_thread_head,
            role_registry=role_registry,
            memory_policy_path=memory_policy_path,
        )
    )
    receipt_ok, receipt_generation = _terminal_receipt(
        runtime,
        contract,
        current_lease=lease,
        assignment_thread_head=assignment_thread_head,
    )
    checks["terminal_sanitized_employee_receipt"] = receipt_ok
    checks["assignment_completed"] = bool(assignment and assignment.state == "completed")
    checks["credential_and_session_identity_not_exposed"] = bool(
        checks["fresh_executor_or_session_live_witness"]
        and checks["private_memory_continuity"]
        and checks["terminal_sanitized_employee_receipt"]
    )
    checks["carrier_and_authority_evidence"] = bool(
        deliveries
        and all(
            item.get("transport") == EXPECTED_TRANSPORT
            and item.get("authority_policy_id") == EXPECTED_AUTHORITY_POLICY
            and item.get("capability") == WAKE_CAPABILITY
            for item in deliveries
        )
    )

    blocking = tuple(name for name, ok in checks.items() if not ok)
    return SpecStewardAcceptanceReport(
        schema=REPORT_SCHEMA,
        employee_id=contract.employee.employee_id,
        assignment_id=contract.initial_work_item.assignment_id,
        checks=checks,
        blocking_reasons=blocking,
        qualifying_delivery_count=len(deliveries),
        qualifying_wake_generations=wake_generations,
        observed_lease_generation=lease.generation if lease else None,
        terminal_receipt_generation=receipt_generation,
        ready_for_live_marker=not blocking,
        verified_marker_emitted=False,
        credential_exposed=False,
        session_identity_exposed=False,
    )

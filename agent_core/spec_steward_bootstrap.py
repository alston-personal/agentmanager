from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_core.core_work_items import WorkItem, WorkItemStore, normalize_work_item
from agent_core.employee_runtime import AgentInstance, EmployeeRuntime
from agent_core.employee_skills import EmployeeSkillRegistry, EmployeeSkillService
from agent_core.role_runtime import EffectiveRoleContract, RoleRegistry


BOOTSTRAP_SCHEMA = "agentos.employee-bootstrap/v1"
BOOTSTRAP_RESULT_SCHEMA = "agentos.spec-steward-bootstrap-result/v1"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = ROOT / "governance" / "spec-steward-employee.json"
DEFAULT_ROLE_REGISTRY_PATH = ROOT / ".agent" / "roles" / "registry.yaml"
DEFAULT_SKILL_REGISTRY_PATH = ROOT / "governance" / "employee-skills.json"

EMPLOYEE_FIELDS = {"employee_id", "display_name", "role_ids", "skill_ids"}
CONTRACT_FIELDS = {
    "schema",
    "bootstrap_id",
    "employee",
    "initial_work_item",
    "initial_thread_head",
    "acceptance_marker",
    "acceptance_requires",
    "invariants",
}


def _nonempty(value: Any, name: str, limit: int = 512) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise ValueError(f"invalid_spec_steward_{name}")
    return text


def _strings(value: Any, name: str, *, max_items: int = 64) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > max_items:
        raise ValueError(f"invalid_spec_steward_{name}")
    result = tuple(_nonempty(item, name, 512) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"duplicate_spec_steward_{name}")
    return result


@dataclass(frozen=True, slots=True)
class DesiredEmployee:
    employee_id: str
    display_name: str
    role_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpecStewardBootstrapContract:
    schema: str
    bootstrap_id: str
    employee: DesiredEmployee
    initial_work_item: WorkItem
    initial_thread_head: str
    acceptance_marker: str
    acceptance_requires: tuple[str, ...]
    invariants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpecStewardBootstrapResult:
    schema: str
    bootstrap_id: str
    employee_id: str
    assignment_id: str
    work_item_id: str
    employee_created: bool
    work_item_created: bool
    assignment_created: bool
    initial_thread_seeded: bool
    assignment_state: str
    thread_head: str
    role_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    role_capabilities: tuple[str, ...]
    hydrated_skill_ids: tuple[str, ...]
    execution_authority: str = "not_granted_by_bootstrap"
    transport_selection: str = "unbound"
    executor_selection: str = "unbound"
    credential_exposed: bool = False
    verified_marker_emitted: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("role_ids", "skill_ids", "role_capabilities", "hydrated_skill_ids"):
            value[key] = list(value[key])
        return value


def load_spec_steward_contract(path: str | Path = DEFAULT_CONTRACT_PATH) -> SpecStewardBootstrapContract:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != BOOTSTRAP_SCHEMA:
        raise ValueError("invalid_spec_steward_bootstrap_schema")
    extra = sorted(set(raw) - CONTRACT_FIELDS)
    if extra:
        raise ValueError("unexpected_spec_steward_bootstrap_fields:" + ",".join(extra))

    employee_raw = raw.get("employee")
    if not isinstance(employee_raw, dict):
        raise ValueError("spec_steward_employee_contract_required")
    extra_employee = sorted(set(employee_raw) - EMPLOYEE_FIELDS)
    if extra_employee:
        raise ValueError("unexpected_spec_steward_employee_fields:" + ",".join(extra_employee))
    employee = DesiredEmployee(
        employee_id=_nonempty(employee_raw.get("employee_id"), "employee_id", 180),
        display_name=_nonempty(employee_raw.get("display_name"), "display_name", 180),
        role_ids=_strings(employee_raw.get("role_ids"), "role_ids"),
        skill_ids=_strings(employee_raw.get("skill_ids"), "skill_ids"),
    )
    work_item = normalize_work_item(raw.get("initial_work_item") or {})
    contract = SpecStewardBootstrapContract(
        schema=BOOTSTRAP_SCHEMA,
        bootstrap_id=_nonempty(raw.get("bootstrap_id"), "bootstrap_id", 180),
        employee=employee,
        initial_work_item=work_item,
        initial_thread_head=_nonempty(raw.get("initial_thread_head"), "initial_thread_head", 512),
        acceptance_marker=_nonempty(raw.get("acceptance_marker"), "acceptance_marker", 180),
        acceptance_requires=_strings(raw.get("acceptance_requires"), "acceptance_requires"),
        invariants=_strings(raw.get("invariants"), "invariants"),
    )
    if contract.employee.role_ids != ("governance.spec_steward",):
        raise ValueError("spec_steward_role_contract_must_be_exact")
    if contract.employee.skill_ids != ("spec.audit",):
        raise ValueError("spec_steward_skill_contract_must_be_exact")
    if contract.initial_work_item.employee_id != contract.employee.employee_id:
        raise ValueError("spec_steward_work_item_employee_mismatch")
    if contract.initial_work_item.project_id != "agentos-core":
        raise ValueError("spec_steward_project_scope_mismatch")
    if contract.initial_work_item.source_ref != "core:issue-197-o3":
        raise ValueError("spec_steward_source_scope_mismatch")
    if contract.acceptance_marker != "SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED":
        raise ValueError("spec_steward_acceptance_marker_mismatch")
    return contract


def _validate_machine_contracts(
    contract: SpecStewardBootstrapContract,
    role_registry: RoleRegistry,
    skill_registry: EmployeeSkillRegistry,
) -> tuple[list[EffectiveRoleContract], tuple[str, ...]]:
    roles = [role_registry.resolve(role_id) for role_id in contract.employee.role_ids]
    role_capabilities = tuple(sorted({cap for role in roles for cap in role.capabilities}))
    missing_work = sorted(
        set(contract.initial_work_item.required_capabilities) - set(role_capabilities)
    )
    if missing_work:
        raise PermissionError(
            "spec_steward_work_item_missing_role_capability:" + ",".join(missing_work)
        )

    for skill_id in contract.employee.skill_ids:
        skill = skill_registry.resolve(skill_id)
        missing_skill = sorted(set(skill.required_capabilities) - set(role_capabilities))
        if missing_skill:
            raise PermissionError(
                "spec_steward_skill_missing_role_capability:" + ",".join(missing_skill)
            )
        if skill.mutation_authority is not False:
            raise PermissionError("spec_steward_skill_mutation_authority_forbidden")
    return roles, role_capabilities


def _assert_existing_employee_matches(employee: AgentInstance, desired: DesiredEmployee) -> None:
    if (
        employee.agent_id != desired.employee_id
        or employee.display_name != desired.display_name
        or tuple(employee.role_ids) != desired.role_ids
        or tuple(employee.skill_ids) != desired.skill_ids
        or employee.memory_namespace != f"employee:{desired.employee_id}"
    ):
        raise RuntimeError("spec_steward_employee_contract_conflict")


def ensure_spec_steward(
    runtime: EmployeeRuntime,
    *,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    role_registry_path: str | Path = DEFAULT_ROLE_REGISTRY_PATH,
    skill_registry_path: str | Path = DEFAULT_SKILL_REGISTRY_PATH,
) -> SpecStewardBootstrapResult:
    """Idempotently materialize the declared Spec Steward Employee and bounded O3 assignment.

    This writes only the supplied EmployeeRuntime. It does not bind an executor,
    create Employee presence, choose transport, enable the Supervisor, dispatch ONE
    work, or emit the O3 VERIFIED marker.
    """
    contract = load_spec_steward_contract(contract_path)
    role_registry = RoleRegistry(role_registry_path)
    skill_registry = EmployeeSkillRegistry(skill_registry_path)
    _roles, role_capabilities = _validate_machine_contracts(
        contract, role_registry, skill_registry
    )

    employee_created = False
    try:
        employee = runtime.get_employee(contract.employee.employee_id)
        _assert_existing_employee_matches(employee, contract.employee)
    except FileNotFoundError:
        employee = runtime.create_employee(
            contract.employee.employee_id,
            contract.employee.display_name,
            role_ids=list(contract.employee.role_ids),
            skill_ids=list(contract.employee.skill_ids),
        )
        employee_created = True

    skill_service = EmployeeSkillService(runtime, role_registry, skill_registry)
    hydrated_skills = skill_service.hydrate_employee_skills(employee.agent_id)

    store = WorkItemStore(runtime)
    work_item_path = store.root / f"{contract.initial_work_item.work_item_id}.json"
    work_item_created = not work_item_path.exists()
    store.persist(contract.initial_work_item.as_dict())

    assignment_path = runtime.assignments_dir / f"{contract.initial_work_item.assignment_id}.json"
    assignment_created = not assignment_path.exists()
    assignment = store.project_pending_assignment(contract.initial_work_item.work_item_id)

    initial_thread_seeded = False
    if not assignment.thread_head and assignment.state == "pending":
        assignment = runtime.update_assignment(
            assignment.assignment_id,
            thread_head=contract.initial_thread_head,
        )
        initial_thread_seeded = True
    # Never reset a progressed/terminal assignment or overwrite a checkpoint.

    return SpecStewardBootstrapResult(
        schema=BOOTSTRAP_RESULT_SCHEMA,
        bootstrap_id=contract.bootstrap_id,
        employee_id=employee.agent_id,
        assignment_id=assignment.assignment_id,
        work_item_id=contract.initial_work_item.work_item_id,
        employee_created=employee_created,
        work_item_created=work_item_created,
        assignment_created=assignment_created,
        initial_thread_seeded=initial_thread_seeded,
        assignment_state=assignment.state,
        thread_head=assignment.thread_head,
        role_ids=tuple(employee.role_ids),
        skill_ids=tuple(employee.skill_ids),
        role_capabilities=role_capabilities,
        hydrated_skill_ids=tuple(skill.skill_id for skill in hydrated_skills),
    )


def build_spec_steward_audit_request(
    runtime: EmployeeRuntime,
    *,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    role_registry_path: str | Path = DEFAULT_ROLE_REGISTRY_PATH,
    skill_registry_path: str | Path = DEFAULT_SKILL_REGISTRY_PATH,
) -> dict[str, Any]:
    """Build a bounded skill intent only; downstream capability authority is still required."""
    contract = load_spec_steward_contract(contract_path)
    service = EmployeeSkillService(
        runtime,
        RoleRegistry(role_registry_path),
        EmployeeSkillRegistry(skill_registry_path),
    )
    return service.build_request(
        contract.employee.employee_id,
        "spec.audit",
        "audit",
        {
            "scope": "core-issue-197-o3",
            "target_refs": ["core:issue-197", "core:employee-runtime"],
        },
    )

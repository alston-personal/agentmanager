from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry


SKILL_REGISTRY_SCHEMA = "agentos.employee-skills/v1"
SKILL_REQUEST_SCHEMA = "agentos.employee-skill-request/v1"
MAX_ARGS_JSON_BYTES = 8192
FORBIDDEN_CONTRACT_KEYS = {
    "argv",
    "executable",
    "command",
    "shell",
    "url",
    "endpoint",
    "credential",
    "credentials",
    "token",
    "secret",
    "authorization",
    "headers",
    "env",
    "environment",
}
SECRET_MARKERS = (
    "bearer ",
    "github_pat_",
    "ghp_",
    "token=",
    "secret=",
    "authorization:",
)


@dataclass(frozen=True, slots=True)
class HydratedEmployeeSkill:
    skill_id: str
    version: str
    purpose: str
    required_capabilities: tuple[str, ...]
    allowed_intents: tuple[str, ...]
    input_fields: tuple[str, ...]
    output_types: tuple[str, ...]
    mutation_authority: bool

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "required_capabilities",
            "allowed_intents",
            "input_fields",
            "output_types",
        ):
            value[key] = list(value[key])
        return value


def _assert_no_forbidden_contract_fields(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().casefold()
            if key in FORBIDDEN_CONTRACT_KEYS:
                raise ValueError(f"forbidden_skill_contract_field:{path}.{key}")
            _assert_no_forbidden_contract_fields(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_contract_fields(item, path=f"{path}[{index}]")


def _assert_safe_request_value(value: Any, *, path: str = "args") -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().casefold()
            if key in FORBIDDEN_CONTRACT_KEYS:
                raise ValueError(f"forbidden_skill_request_field:{path}.{key}")
            _assert_safe_request_value(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe_request_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        lowered = value.casefold()
        if "://" in value or any(marker in lowered for marker in SECRET_MARKERS):
            raise ValueError(f"unsafe_skill_request_value:{path}")
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValueError(f"unsupported_skill_request_value:{path}")


class EmployeeSkillRegistry:
    """Machine-readable skill contracts with no embedded execution carrier."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("employee_skill_registry_must_be_object")
        if raw.get("schema") != SKILL_REGISTRY_SCHEMA:
            raise ValueError("unsupported_employee_skill_registry_schema")
        if raw.get("default_effect") != "deny":
            raise ValueError("employee_skill_registry_must_default_deny")
        skills = raw.get("skills")
        if not isinstance(skills, dict):
            raise ValueError("employee_skill_registry_skills_required")
        _assert_no_forbidden_contract_fields(skills, path="skills")
        self._skills: dict[str, dict[str, Any]] = {}
        for raw_id, raw_skill in skills.items():
            skill_id = str(raw_id).strip()
            if not skill_id or skill_id == "*" or not isinstance(raw_skill, dict):
                raise ValueError("invalid_employee_skill_entry")
            self._skills[skill_id] = raw_skill

    def resolve(self, skill_id: str) -> HydratedEmployeeSkill:
        skill_id = str(skill_id or "").strip()
        raw = self._skills.get(skill_id)
        if raw is None:
            raise KeyError(f"unknown_employee_skill:{skill_id}")
        if raw.get("status") != "active":
            raise ValueError(f"employee_skill_not_active:{skill_id}")
        if raw.get("mutation_authority") is not False:
            raise ValueError(f"employee_skill_mutation_authority_forbidden:{skill_id}")

        def tuple_field(name: str) -> tuple[str, ...]:
            value = raw.get(name, [])
            if not isinstance(value, list):
                raise ValueError(f"employee_skill_{name}_must_be_list:{skill_id}")
            result = tuple(str(item).strip() for item in value)
            if any(not item or item == "*" for item in result):
                raise ValueError(f"employee_skill_{name}_wildcard_forbidden:{skill_id}")
            return result

        return HydratedEmployeeSkill(
            skill_id=skill_id,
            version=str(raw.get("version") or ""),
            purpose=str(raw.get("purpose") or ""),
            required_capabilities=tuple_field("required_capabilities"),
            allowed_intents=tuple_field("allowed_intents"),
            input_fields=tuple_field("input_fields"),
            output_types=tuple_field("output_types"),
            mutation_authority=False,
        )


class EmployeeSkillService:
    """Hydrate skill contracts only when role authority covers their requirements."""

    def __init__(
        self,
        runtime: EmployeeRuntime,
        role_registry: RoleRegistry,
        skill_registry: EmployeeSkillRegistry,
    ) -> None:
        self.runtime = runtime
        self.role_registry = role_registry
        self.skill_registry = skill_registry

    def hydrate_employee_skills(self, employee_id: str) -> list[HydratedEmployeeSkill]:
        employee = self.runtime.get_employee(employee_id)
        roles = self.role_registry.hydrate_employee_roles(list(employee.role_ids))
        role_capabilities = {
            capability
            for role in roles
            for capability in role.capabilities
        }
        hydrated: list[HydratedEmployeeSkill] = []
        for skill_id in employee.skill_ids:
            skill = self.skill_registry.resolve(skill_id)
            missing = sorted(
                set(skill.required_capabilities) - role_capabilities
            )
            if missing:
                raise PermissionError(
                    "employee_skill_missing_role_capability:"
                    + skill.skill_id
                    + ":"
                    + ",".join(missing)
                )
            hydrated.append(skill)
        return hydrated

    def build_request(
        self,
        employee_id: str,
        skill_id: str,
        intent: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        employee = self.runtime.get_employee(employee_id)
        hydrated = {
            skill.skill_id: skill
            for skill in self.hydrate_employee_skills(employee_id)
        }
        skill = hydrated.get(skill_id)
        if skill is None:
            raise PermissionError("employee_skill_not_assigned")
        intent = str(intent or "").strip()
        if intent not in skill.allowed_intents:
            raise PermissionError("employee_skill_intent_not_allowed")
        arguments = dict(args or {})
        unexpected = sorted(set(arguments) - set(skill.input_fields))
        if unexpected:
            raise ValueError(
                "employee_skill_unexpected_input:" + ",".join(unexpected)
            )
        _assert_safe_request_value(arguments)
        encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        if len(encoded) > MAX_ARGS_JSON_BYTES:
            raise ValueError("employee_skill_request_too_large")

        return {
            "schema": SKILL_REQUEST_SCHEMA,
            "employee_id": employee.agent_id,
            "skill": skill.as_dict(),
            "intent": intent,
            "args": arguments,
            "capability_authorization": "required_downstream",
            "execution_authority": "external_governed_dispatcher",
            "executor_selection": "unbound",
            "transport_selection": "unbound",
            "credential_exposed": False,
        }

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry


MEMORY_POLICY_SCHEMA = "agentos.employee-memory-policy/v1"
MEMORY_DECISION_SCHEMA = "agentos.employee-memory-decision/v1"
VALID_OPERATIONS = {"read", "write"}


@dataclass(frozen=True, slots=True)
class EmployeeMemoryDecision:
    schema: str
    employee_id: str
    memory_class: str
    operation: str
    allowed: bool
    authorizing_roles: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["authorizing_roles"] = list(self.authorizing_roles)
        return value


class EmployeeMemoryPolicy:
    """Explicit deny-by-default role -> private-memory-class policy."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("employee_memory_policy_must_be_object")
        if raw.get("schema") != MEMORY_POLICY_SCHEMA:
            raise ValueError("unsupported_employee_memory_policy_schema")
        if raw.get("default_effect") != "deny":
            raise ValueError("employee_memory_policy_must_default_deny")
        if raw.get("cross_employee_access") != "deny":
            raise ValueError("cross_employee_memory_must_default_deny")

        classes = raw.get("memory_classes")
        rules = raw.get("role_rules")
        if not isinstance(classes, list) or not classes:
            raise ValueError("memory_classes_required")
        if not isinstance(rules, dict):
            raise ValueError("role_rules_required")

        self.memory_classes = frozenset(str(value) for value in classes)
        if "*" in self.memory_classes or any(not value.strip() for value in self.memory_classes):
            raise ValueError("memory_class_wildcards_not_allowed")

        normalized: dict[str, dict[str, frozenset[str]]] = {}
        for role_id, rule in rules.items():
            role_id = str(role_id).strip()
            if not role_id or role_id == "*" or not isinstance(rule, dict):
                raise ValueError("invalid_memory_role_rule")
            normalized[role_id] = {}
            for operation in VALID_OPERATIONS:
                values = rule.get(operation, [])
                if not isinstance(values, list):
                    raise ValueError("memory_role_rule_must_be_list")
                allowed = frozenset(str(value) for value in values)
                if "*" in allowed or not allowed.issubset(self.memory_classes):
                    raise ValueError("invalid_memory_class_grant")
                normalized[role_id][operation] = allowed
        self.role_rules = normalized

    def grants(self, role_id: str, operation: str) -> frozenset[str]:
        if operation not in VALID_OPERATIONS:
            raise ValueError("invalid_memory_operation")
        return self.role_rules.get(role_id, {}).get(operation, frozenset())


class EmployeeMemoryService:
    """Policy-enforced private Employee memory.

    Memory is currently self-only.  Cross-Employee knowledge transfer must use a
    governed message/handoff/public knowledge surface rather than reading another
    Employee's private memory directory.  Executor identity never participates in
    authorization.
    """

    def __init__(
        self,
        runtime: EmployeeRuntime,
        role_registry: RoleRegistry,
        policy: EmployeeMemoryPolicy,
    ) -> None:
        self.runtime = runtime
        self.role_registry = role_registry
        self.policy = policy

    def authorize(
        self,
        caller_employee_id: str,
        target_employee_id: str,
        memory_class: str,
        operation: str,
    ) -> EmployeeMemoryDecision:
        operation = str(operation).strip().lower()
        memory_class = str(memory_class).strip()
        if operation not in VALID_OPERATIONS:
            raise ValueError("invalid_memory_operation")

        caller = self.runtime.get_employee(caller_employee_id)
        self.runtime.get_employee(target_employee_id)
        if caller.agent_id != target_employee_id:
            return EmployeeMemoryDecision(
                schema=MEMORY_DECISION_SCHEMA,
                employee_id=caller.agent_id,
                memory_class=memory_class,
                operation=operation,
                allowed=False,
                authorizing_roles=(),
                reason="cross_employee_private_memory_denied",
            )
        if memory_class not in self.policy.memory_classes:
            return EmployeeMemoryDecision(
                schema=MEMORY_DECISION_SCHEMA,
                employee_id=caller.agent_id,
                memory_class=memory_class,
                operation=operation,
                allowed=False,
                authorizing_roles=(),
                reason="unknown_memory_class",
            )
        if not caller.role_ids:
            return EmployeeMemoryDecision(
                schema=MEMORY_DECISION_SCHEMA,
                employee_id=caller.agent_id,
                memory_class=memory_class,
                operation=operation,
                allowed=False,
                authorizing_roles=(),
                reason="active_role_required",
            )

        # Fail the entire request if any role reference cannot be machine-hydrated
        # as active.  A proposed/stale role must never accidentally coexist with an
        # active role and inherit that role's memory authority.
        self.role_registry.hydrate_employee_roles(list(caller.role_ids))
        granting = tuple(
            sorted(
                role_id
                for role_id in caller.role_ids
                if memory_class in self.policy.grants(role_id, operation)
            )
        )
        return EmployeeMemoryDecision(
            schema=MEMORY_DECISION_SCHEMA,
            employee_id=caller.agent_id,
            memory_class=memory_class,
            operation=operation,
            allowed=bool(granting),
            authorizing_roles=granting,
            reason="explicit_role_grant" if granting else "no_explicit_role_grant",
        )

    def write(
        self,
        employee_id: str,
        memory_class: str,
        key: str,
        value: Any,
    ) -> EmployeeMemoryDecision:
        decision = self.authorize(
            employee_id, employee_id, memory_class, "write"
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        self.runtime._write_memory_record(  # noqa: SLF001 - policy boundary primitive
            employee_id, memory_class, key, value
        )
        return decision

    def read(self, employee_id: str, memory_class: str, key: str) -> Any:
        decision = self.authorize(
            employee_id, employee_id, memory_class, "read"
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return self.runtime._read_memory_record(  # noqa: SLF001 - policy boundary primitive
            employee_id, memory_class, key
        )

    def read_other(
        self,
        caller_employee_id: str,
        target_employee_id: str,
        memory_class: str,
        key: str,
    ) -> Any:
        decision = self.authorize(
            caller_employee_id, target_employee_id, memory_class, "read"
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        # cross_employee_access is policy-fixed deny in v1, so this line is not
        # reachable today.  It exists to keep authorization and storage semantics
        # explicit if a future policy version introduces a governed shared scope.
        return self.runtime._read_memory_record(  # noqa: SLF001
            target_employee_id, memory_class, key
        )

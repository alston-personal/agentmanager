from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class EffectiveRoleContract:
    role_id: str
    name: str
    kind: str
    status: str
    source: str | None
    purpose: str
    must_obey: list[str] = field(default_factory=list)
    may: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    upstream_roles: list[str] = field(default_factory=list)
    handoff_to: list[str] = field(default_factory=list)


class RoleRegistry:
    """Machine-hydrates role contracts from the canonical role registry.

    The registry is authoritative for role identity/status/relationships. Human-readable
    source documents remain supporting contract text; runtime must not infer authority
    by scraping arbitrary prose.
    """

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)
        raw = yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or {}
        roles = raw.get("roles", [])
        if not isinstance(roles, list):
            raise ValueError("role registry roles must be a list")
        self.schema_version = str(raw.get("schema_version", ""))
        self.role_set_version = str(raw.get("role_set_version", ""))
        self._roles: dict[str, dict[str, Any]] = {}
        for role in roles:
            if not isinstance(role, dict) or not role.get("id"):
                raise ValueError("each role must be an object with id")
            role_id = str(role["id"])
            if role_id in self._roles:
                raise ValueError(f"duplicate role id: {role_id}")
            self._roles[role_id] = role

    def ids(self, *, include_proposed: bool = False) -> list[str]:
        result = []
        for role_id, role in self._roles.items():
            if include_proposed or role.get("status") == "active":
                result.append(role_id)
        return sorted(result)

    def resolve(self, role_id: str) -> EffectiveRoleContract:
        if role_id not in self._roles:
            raise KeyError(role_id)
        role = self._roles[role_id]
        if role.get("status") != "active":
            raise ValueError(f"role is not active: {role_id}")

        visited: set[str] = set()
        ordered: list[dict[str, Any]] = []

        def walk(current_id: str) -> None:
            if current_id in visited:
                return
            visited.add(current_id)
            current = self._roles.get(current_id)
            if current is None:
                raise KeyError(f"unknown upstream role: {current_id}")
            if current.get("status") != "active":
                raise ValueError(f"upstream role is not active: {current_id}")
            for parent in current.get("upstream_roles", []) or []:
                walk(str(parent))
            ordered.append(current)

        walk(role_id)

        def merged_list(key: str) -> list[str]:
            result: list[str] = []
            for item in ordered:
                for value in item.get(key, []) or []:
                    value = str(value)
                    if value not in result:
                        result.append(value)
            return result

        return EffectiveRoleContract(
            role_id=role_id,
            name=str(role.get("name", role_id)),
            kind=str(role.get("kind", "")),
            status=str(role.get("status", "")),
            source=role.get("source"),
            purpose=str(role.get("purpose", "")),
            must_obey=merged_list("must_obey"),
            may=merged_list("may"),
            must_not=merged_list("must_not"),
            capabilities=merged_list("capabilities"),
            outputs=merged_list("outputs"),
            upstream_roles=[str(value) for value in (role.get("upstream_roles", []) or [])],
            handoff_to=[str(value) for value in (role.get("handoff_to", []) or [])],
        )

    def hydrate_employee_roles(self, role_ids: list[str]) -> list[EffectiveRoleContract]:
        if not role_ids:
            raise ValueError("employee must have at least one role")
        return [self.resolve(role_id) for role_id in role_ids]

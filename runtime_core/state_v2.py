"""Portable AgentOS v2 project-state and delta primitives.

These types deliberately contain no runtime/provider/host dependencies. A model
may propose a StateDelta, but only the trusted State Kernel may turn it into a
canonical ProjectState commit.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable


STATE_SCHEMA_VERSION = "agentos.state/v2"
DELTA_SCHEMA_VERSION = "agentos.delta/v1"
PROTECTED_ROOT_FIELDS = {"schema_version", "project_id", "state_id"}
SUPPORTED_OPS = {"set", "remove", "add_unique"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_path(path: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(str(part) for part in path)
    if not normalized:
        raise ValueError("state operation path cannot be empty")
    if normalized[0] in PROTECTED_ROOT_FIELDS:
        raise ValueError(f"state operation cannot modify protected field {normalized[0]}")
    if any(not part for part in normalized):
        raise ValueError("state operation path segments cannot be empty")
    return normalized


def _paths_conflict(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    common = min(len(left), len(right))
    return left[:common] == right[:common]


@dataclass(frozen=True)
class ProjectState:
    project_id: str
    goal: str
    constraints: tuple[str, ...] = ()
    work_items: dict[str, dict[str, Any]] = field(default_factory=dict)
    decision_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported project state schema: {self.schema_version}")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.goal:
            raise ValueError("goal is required")

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "goal": self.goal,
            "constraints": list(self.constraints),
            "work_items": deepcopy(self.work_items),
            "decision_refs": list(self.decision_refs),
            "artifact_refs": list(self.artifact_refs),
            "memory_refs": list(self.memory_refs),
            "metadata": deepcopy(self.metadata),
        }

    @property
    def state_id(self) -> str:
        return "state_" + _digest(self.content_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.content_dict()
        payload["state_id"] = self.state_id
        return payload

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProjectState":
        if not isinstance(value, dict):
            raise ValueError("project state must be an object")
        state = cls(
            project_id=str(value.get("project_id") or ""),
            goal=str(value.get("goal") or ""),
            constraints=tuple(str(item) for item in (value.get("constraints") or [])),
            work_items=deepcopy(value.get("work_items") or {}),
            decision_refs=tuple(str(item) for item in (value.get("decision_refs") or [])),
            artifact_refs=tuple(str(item) for item in (value.get("artifact_refs") or [])),
            memory_refs=tuple(str(item) for item in (value.get("memory_refs") or [])),
            metadata=deepcopy(value.get("metadata") or {}),
            schema_version=str(value.get("schema_version") or STATE_SCHEMA_VERSION),
        )
        announced = value.get("state_id")
        if announced is not None and announced != state.state_id:
            raise ValueError("project state content hash mismatch")
        return state


@dataclass(frozen=True)
class StateOperation:
    op: str
    path: tuple[str, ...]
    value: Any = None

    def __post_init__(self) -> None:
        if self.op not in SUPPORTED_OPS:
            raise ValueError(f"unsupported state operation: {self.op}")
        object.__setattr__(self, "path", _normalize_path(self.path))
        if self.op == "remove" and self.value is not None:
            raise ValueError("remove operation cannot carry a value")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"op": self.op, "path": list(self.path)}
        if self.op != "remove":
            payload["value"] = deepcopy(self.value)
        return payload

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StateOperation":
        if not isinstance(value, dict):
            raise ValueError("state operation must be an object")
        raw_path = value.get("path")
        if not isinstance(raw_path, list):
            raise ValueError("state operation path must be an array")
        return cls(str(value.get("op") or ""), tuple(str(part) for part in raw_path), value.get("value"))


@dataclass(frozen=True)
class StateDelta:
    project_id: str
    base_state_id: str
    operations: tuple[StateOperation, ...]
    work_id: str | None = None
    schema_version: str = DELTA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DELTA_SCHEMA_VERSION:
            raise ValueError(f"unsupported state delta schema: {self.schema_version}")
        if not self.project_id or not self.base_state_id:
            raise ValueError("project_id and base_state_id are required")
        if not self.operations:
            raise ValueError("state delta must contain at least one operation")

    @property
    def touched_paths(self) -> tuple[tuple[str, ...], ...]:
        return tuple(operation.path for operation in self.operations)

    @property
    def delta_id(self) -> str:
        return "delta_" + _digest(self.to_dict(include_delta_id=False))

    def to_dict(self, *, include_delta_id: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "base_state_id": self.base_state_id,
            "operations": [operation.to_dict() for operation in self.operations],
        }
        if self.work_id:
            payload["work_id"] = self.work_id
        if include_delta_id:
            payload["delta_id"] = self.delta_id
        return payload

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StateDelta":
        if not isinstance(value, dict):
            raise ValueError("state delta must be an object")
        operations = value.get("operations")
        if not isinstance(operations, list):
            raise ValueError("state delta operations must be an array")
        delta = cls(
            project_id=str(value.get("project_id") or ""),
            base_state_id=str(value.get("base_state_id") or ""),
            operations=tuple(StateOperation.from_dict(item) for item in operations),
            work_id=str(value["work_id"]) if value.get("work_id") else None,
            schema_version=str(value.get("schema_version") or DELTA_SCHEMA_VERSION),
        )
        announced = value.get("delta_id")
        if announced is not None and announced != delta.delta_id:
            raise ValueError("state delta content hash mismatch")
        return delta


def _parent(document: Any, path: tuple[str, ...], *, create: bool) -> tuple[Any, str]:
    current = document
    for segment in path[:-1]:
        if not isinstance(current, dict):
            raise ValueError(f"cannot traverse non-object state at {'/'.join(path)}")
        if segment not in current:
            if not create:
                raise KeyError("/".join(path))
            current[segment] = {}
        child = current[segment]
        if not isinstance(child, dict):
            raise ValueError(f"cannot traverse non-object state at {'/'.join(path)}")
        current = child
    return current, path[-1]


def apply_delta(state: ProjectState, delta: StateDelta) -> ProjectState:
    if state.project_id != delta.project_id:
        raise ValueError("delta project does not match project state")
    document = state.content_dict()
    for operation in delta.operations:
        parent, key = _parent(document, operation.path, create=operation.op == "set")
        if not isinstance(parent, dict):
            raise ValueError("state operation parent must be an object")
        if operation.op == "set":
            parent[key] = deepcopy(operation.value)
        elif operation.op == "remove":
            if key not in parent:
                raise KeyError("/".join(operation.path))
            del parent[key]
        elif operation.op == "add_unique":
            target = parent.get(key)
            if not isinstance(target, list):
                raise ValueError(f"add_unique target {'/'.join(operation.path)} must be an array")
            if operation.value not in target:
                target.append(deepcopy(operation.value))
        else:  # pragma: no cover - guarded by StateOperation
            raise ValueError(f"unsupported state operation: {operation.op}")
    return ProjectState.from_dict(document)


def changed_paths(base: ProjectState, current: ProjectState) -> set[tuple[str, ...]]:
    if base.project_id != current.project_id:
        raise ValueError("cannot compare states from different projects")
    changed: set[tuple[str, ...]] = set()

    def walk(left: Any, right: Any, path: tuple[str, ...]) -> None:
        if type(left) is not type(right):
            if path:
                changed.add(path)
            return
        if isinstance(left, dict):
            keys = set(left) | set(right)
            for key in keys:
                child_path = path + (str(key),)
                if key not in left or key not in right:
                    changed.add(child_path)
                else:
                    walk(left[key], right[key], child_path)
            return
        if isinstance(left, list):
            if left != right and path:
                changed.add(path)
            return
        if left != right and path:
            changed.add(path)

    walk(base.content_dict(), current.content_dict(), ())
    return {path for path in changed if path and path[0] not in PROTECTED_ROOT_FIELDS}


def conflicting_paths(
    base: ProjectState,
    current: ProjectState,
    delta: StateDelta,
) -> set[tuple[str, ...]]:
    """Return paths that make a stale delta unsafe to auto-merge.

    `add_unique` is intentionally commutative for list-valued reference sets, so
    concurrent additions to the same list are allowed as long as the list type
    still exists in current state.
    """
    changed = changed_paths(base, current)
    conflicts: set[tuple[str, ...]] = set()
    current_doc = current.content_dict()

    for operation in delta.operations:
        if operation.op == "add_unique":
            try:
                parent, key = _parent(current_doc, operation.path, create=False)
                if isinstance(parent, dict) and isinstance(parent.get(key), list):
                    continue
            except (KeyError, ValueError):
                pass
        for changed_path in changed:
            if _paths_conflict(operation.path, changed_path):
                conflicts.add(operation.path)
                break
    return conflicts

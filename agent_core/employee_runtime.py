from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_ASSIGNMENT_STATES = {"pending", "active", "blocked", "handoff", "completed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    value = value.strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError(f"unsafe id: {value!r}")
    return value


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


@dataclass(slots=True)
class ExecutorBinding:
    provider: str = "unbound"
    model: str = ""
    session_id: str = ""
    bound_at: str = ""


@dataclass(slots=True)
class AgentInstance:
    agent_id: str
    display_name: str
    role_ids: list[str] = field(default_factory=list)
    skill_ids: list[str] = field(default_factory=list)
    memory_namespace: str = ""
    executor: ExecutorBinding = field(default_factory=ExecutorBinding)
    status: str = "available"
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class Assignment:
    assignment_id: str
    goal: str
    employee_id: str
    state: str = "pending"
    parent_assignment_id: str | None = None
    thread_head: str = ""
    constraints: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class AgentMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    subject: str
    payload: dict[str, Any]
    assignment_id: str | None = None
    created_at: str = ""
    read_at: str = ""


class EmployeeRuntime:
    """Minimal durable employee kernel.

    Agent identity and working ownership live outside any LLM/provider. An executor
    binding can be replaced without replacing the employee or its durable state.
    This module intentionally implements mechanics only; role intelligence remains
    in role/skill contracts and higher-level orchestrators.
    """

    def __init__(self, data_root: str | Path | None = None) -> None:
        root = data_root or os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data"
        self.root = Path(root).expanduser().resolve() / "employees"
        self.root.mkdir(parents=True, exist_ok=True)

    def _employee_dir(self, agent_id: str) -> Path:
        return self.root / _safe_id(agent_id)

    def _employee_path(self, agent_id: str) -> Path:
        return self._employee_dir(agent_id) / "employee.json"

    def _assignments_path(self, agent_id: str) -> Path:
        return self._employee_dir(agent_id) / "assignments.json"

    def _inbox_path(self, agent_id: str) -> Path:
        return self._employee_dir(agent_id) / "inbox.json"

    def _outbox_path(self, agent_id: str) -> Path:
        return self._employee_dir(agent_id) / "outbox.json"

    def memory_dir(self, agent_id: str) -> Path:
        path = self._employee_dir(agent_id) / "memory"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register_employee(self, agent_id: str, *, display_name: str, role_ids: list[str] | None = None, skill_ids: list[str] | None = None, replace: bool = False) -> AgentInstance:
        agent_id = _safe_id(agent_id)
        path = self._employee_path(agent_id)
        if path.exists() and not replace:
            raise ValueError(f"employee already exists: {agent_id}")
        now = _now()
        existing = self.get_employee(agent_id) if path.exists() else None
        employee = AgentInstance(agent_id=agent_id, display_name=display_name, role_ids=list(role_ids or []), skill_ids=list(skill_ids or []), memory_namespace=f"employees/{agent_id}/memory", executor=existing.executor if existing else ExecutorBinding(), status=existing.status if existing else "available", created_at=existing.created_at if existing else now, updated_at=now)
        _atomic_json_write(path, asdict(employee))
        self.memory_dir(agent_id)
        return employee

    def get_employee(self, agent_id: str) -> AgentInstance | None:
        path = self._employee_path(agent_id)
        if not path.exists():
            return None
        data = _read_json(path, {})
        executor = ExecutorBinding(**(data.pop("executor", {}) or {}))
        return AgentInstance(executor=executor, **data)

    def bind_executor(self, agent_id: str, *, provider: str, model: str = "", session_id: str = "") -> AgentInstance:
        employee = self._require_employee(agent_id)
        employee.executor = ExecutorBinding(provider=provider, model=model, session_id=session_id, bound_at=_now())
        employee.updated_at = _now()
        _atomic_json_write(self._employee_path(agent_id), asdict(employee))
        return employee

    def create_assignment(self, assignment_id: str, *, employee_id: str, goal: str, constraints: list[str] | None = None, parent_assignment_id: str | None = None, thread_head: str = "") -> Assignment:
        employee_id = _safe_id(employee_id)
        assignment_id = _safe_id(assignment_id)
        self._require_employee(employee_id)
        data = _read_json(self._assignments_path(employee_id), {"items": {}})
        items = data.setdefault("items", {})
        if assignment_id in items:
            raise ValueError(f"assignment already exists: {assignment_id}")
        now = _now()
        assignment = Assignment(assignment_id=assignment_id, goal=goal, employee_id=employee_id, parent_assignment_id=parent_assignment_id, thread_head=thread_head, constraints=list(constraints or []), created_at=now, updated_at=now)
        items[assignment_id] = asdict(assignment)
        _atomic_json_write(self._assignments_path(employee_id), data)
        return assignment

    def get_assignment(self, employee_id: str, assignment_id: str) -> Assignment | None:
        data = _read_json(self._assignments_path(employee_id), {"items": {}})
        raw = data.get("items", {}).get(assignment_id)
        return Assignment(**raw) if raw else None

    def set_assignment_state(self, employee_id: str, assignment_id: str, state: str, *, thread_head: str | None = None, result: dict[str, Any] | None = None) -> Assignment:
        if state not in VALID_ASSIGNMENT_STATES:
            raise ValueError(f"invalid assignment state: {state}")
        data = _read_json(self._assignments_path(employee_id), {"items": {}})
        raw = data.get("items", {}).get(assignment_id)
        if not raw:
            raise KeyError(assignment_id)
        raw["state"] = state
        raw["updated_at"] = _now()
        if thread_head is not None:
            raw["thread_head"] = thread_head
        if result is not None:
            raw["result"] = result
        data["items"][assignment_id] = raw
        _atomic_json_write(self._assignments_path(employee_id), data)
        return Assignment(**raw)

    def send_message(self, message_id: str, *, sender_id: str, recipient_id: str, subject: str, payload: dict[str, Any], assignment_id: str | None = None) -> AgentMessage:
        message_id = _safe_id(message_id)
        self._require_employee(sender_id)
        self._require_employee(recipient_id)
        now = _now()
        message = AgentMessage(message_id=message_id, sender_id=sender_id, recipient_id=recipient_id, subject=subject, payload=dict(payload), assignment_id=assignment_id, created_at=now)
        self._append_message(self._outbox_path(sender_id), message)
        self._append_message(self._inbox_path(recipient_id), message)
        return message

    def list_inbox(self, agent_id: str) -> list[AgentMessage]:
        self._require_employee(agent_id)
        data = _read_json(self._inbox_path(agent_id), {"items": []})
        return [AgentMessage(**item) for item in data.get("items", [])]

    def _append_message(self, path: Path, message: AgentMessage) -> None:
        data = _read_json(path, {"items": []})
        items = data.setdefault("items", [])
        if any(item.get("message_id") == message.message_id for item in items):
            raise ValueError(f"message already exists: {message.message_id}")
        items.append(asdict(message))
        _atomic_json_write(path, data)

    def _require_employee(self, agent_id: str) -> AgentInstance:
        employee = self.get_employee(agent_id)
        if employee is None:
            raise KeyError(agent_id)
        return employee

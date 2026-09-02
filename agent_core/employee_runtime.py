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
    """Small durable kernel for AgentOS employee identity and assignment state.

    This runtime deliberately stores *references* to roles and skills. Hydrating those
    references into an effective role contract is handled by the role runtime so that
    employee identity stays independent from role-file representation and executor.

    Private Employee memory is a governed resource.  Public callers must use
    ``EmployeeMemoryService``; the storage primitives here are intentionally private
    so role authorization cannot be bypassed by a convenient legacy helper.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.employees_dir = self.root / "employees"
        self.assignments_dir = self.root / "assignments"
        self.messages_dir = self.root / "messages"
        self.memory_dir = self.root / "memory"

    def create_employee(
        self,
        agent_id: str,
        display_name: str,
        *,
        role_ids: list[str] | None = None,
        skill_ids: list[str] | None = None,
    ) -> AgentInstance:
        agent_id = _safe_id(agent_id)
        path = self.employees_dir / f"{agent_id}.json"
        if path.exists():
            raise FileExistsError(f"employee already exists: {agent_id}")
        now = _now()
        employee = AgentInstance(
            agent_id=agent_id,
            display_name=display_name.strip() or agent_id,
            role_ids=list(role_ids or []),
            skill_ids=list(skill_ids or []),
            memory_namespace=f"employee:{agent_id}",
            created_at=now,
            updated_at=now,
        )
        _atomic_json_write(path, asdict(employee))
        return employee

    def get_employee(self, agent_id: str) -> AgentInstance:
        agent_id = _safe_id(agent_id)
        data = _read_json(self.employees_dir / f"{agent_id}.json", {})
        if not data:
            raise FileNotFoundError(agent_id)
        data["executor"] = ExecutorBinding(**data.get("executor", {}))
        return AgentInstance(**data)

    def bind_executor(self, agent_id: str, *, provider: str, model: str = "", session_id: str = "") -> AgentInstance:
        employee = self.get_employee(agent_id)
        employee.executor = ExecutorBinding(
            provider=provider,
            model=model,
            session_id=session_id,
            bound_at=_now(),
        )
        employee.updated_at = _now()
        _atomic_json_write(self.employees_dir / f"{employee.agent_id}.json", asdict(employee))
        return employee

    def create_assignment(
        self,
        assignment_id: str,
        employee_id: str,
        goal: str,
        *,
        parent_assignment_id: str | None = None,
        thread_head: str = "",
        constraints: list[str] | None = None,
    ) -> Assignment:
        assignment_id = _safe_id(assignment_id)
        employee_id = _safe_id(employee_id)
        self.get_employee(employee_id)
        path = self.assignments_dir / f"{assignment_id}.json"
        if path.exists():
            raise FileExistsError(f"assignment already exists: {assignment_id}")
        now = _now()
        assignment = Assignment(
            assignment_id=assignment_id,
            goal=goal,
            employee_id=employee_id,
            parent_assignment_id=parent_assignment_id,
            thread_head=thread_head,
            constraints=list(constraints or []),
            created_at=now,
            updated_at=now,
        )
        _atomic_json_write(path, asdict(assignment))
        return assignment

    def get_assignment(self, assignment_id: str) -> Assignment:
        assignment_id = _safe_id(assignment_id)
        data = _read_json(self.assignments_dir / f"{assignment_id}.json", {})
        if not data:
            raise FileNotFoundError(assignment_id)
        return Assignment(**data)

    def update_assignment(
        self,
        assignment_id: str,
        *,
        state: str | None = None,
        thread_head: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> Assignment:
        assignment = self.get_assignment(assignment_id)
        if state is not None:
            if state not in VALID_ASSIGNMENT_STATES:
                raise ValueError(f"invalid assignment state: {state}")
            assignment.state = state
        if thread_head is not None:
            assignment.thread_head = thread_head
        if result is not None:
            assignment.result = result
        assignment.updated_at = _now()
        _atomic_json_write(self.assignments_dir / f"{assignment.assignment_id}.json", asdict(assignment))
        return assignment

    def write_memory(self, agent_id: str, key: str, value: Any) -> None:
        """Deprecated unscoped entrypoint; intentionally fails closed."""
        raise PermissionError("employee_memory_policy_required")

    def read_memory(self, agent_id: str, key: str) -> Any:
        """Deprecated unscoped entrypoint; intentionally fails closed."""
        raise PermissionError("employee_memory_policy_required")

    def _write_memory_record(
        self,
        agent_id: str,
        memory_class: str,
        key: str,
        value: Any,
    ) -> None:
        """Storage primitive for EmployeeMemoryService after policy authorization."""
        agent_id = _safe_id(agent_id)
        self.get_employee(agent_id)
        memory_class = _safe_id(memory_class)
        key = _safe_id(key)
        path = self.memory_dir / agent_id / memory_class / f"{key}.json"
        _atomic_json_write(
            path,
            {
                "memory_class": memory_class,
                "value": value,
                "updated_at": _now(),
            },
        )

    def _read_memory_record(
        self,
        agent_id: str,
        memory_class: str,
        key: str,
    ) -> Any:
        """Storage primitive for EmployeeMemoryService after policy authorization."""
        agent_id = _safe_id(agent_id)
        self.get_employee(agent_id)
        memory_class = _safe_id(memory_class)
        key = _safe_id(key)
        data = _read_json(
            self.memory_dir / agent_id / memory_class / f"{key}.json",
            {},
        )
        if not data:
            raise FileNotFoundError(key)
        if data.get("memory_class") != memory_class:
            raise ValueError("employee_memory_class_mismatch")
        return data.get("value")

    def send_message(
        self,
        message_id: str,
        sender_id: str,
        recipient_id: str,
        subject: str,
        payload: dict[str, Any],
        *,
        assignment_id: str | None = None,
    ) -> AgentMessage:
        message_id = _safe_id(message_id)
        sender_id = _safe_id(sender_id)
        recipient_id = _safe_id(recipient_id)
        self.get_employee(sender_id)
        self.get_employee(recipient_id)
        now = _now()
        message = AgentMessage(
            message_id=message_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            subject=subject,
            payload=payload,
            assignment_id=assignment_id,
            created_at=now,
        )
        path = self.messages_dir / recipient_id / f"{message_id}.json"
        if path.exists():
            raise FileExistsError(f"message already exists: {message_id}")
        _atomic_json_write(path, asdict(message))
        return message

    def list_inbox(self, agent_id: str) -> list[AgentMessage]:
        agent_id = _safe_id(agent_id)
        inbox = self.messages_dir / agent_id
        if not inbox.exists():
            return []
        messages: list[AgentMessage] = []
        for path in sorted(inbox.glob("*.json")):
            messages.append(AgentMessage(**_read_json(path, {})))
        return messages

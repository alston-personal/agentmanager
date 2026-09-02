from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from agent_core.employee_runtime import EmployeeRuntime

EVENT_SCHEMA = "agentos.core-supervisor-event/v1"
WORK_ITEM_SCHEMA = "agentos.core-work-item/v1"
WORK_ITEM_STATES = {"open", "completed", "cancelled"}
ISSUE_EVENT_TYPES = {"opened", "updated", "reopened", "closed", "labeled", "unlabeled", "assigned", "unassigned", "commented"}
ALLOWED_FIELDS = {
    "schema", "work_item_id", "source_kind", "source_ref", "project_id",
    "employee_id", "assignment_id", "goal", "constraints", "dependency_refs",
    "required_capabilities", "authority_requirements", "source_revision", "state",
}


def _id(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 180 or any(ch in text for ch in "/\\\0") or text in {".", ".."}:
        raise ValueError(f"invalid_{name}")
    return text


def _text(value: Any, name: str, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise ValueError(f"invalid_{name}")
    return text


def _ref(value: Any, name: str) -> str:
    text = _text(value, name, 512)
    if "://" in text or text.startswith(("/", "~")) or "\\" in text or ":" not in text:
        raise ValueError(f"invalid_{name}")
    return text


def _strings(value: Any, name: str, max_items: int = 64) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > max_items:
        raise ValueError(f"invalid_{name}")
    result = tuple(str(item or "").strip() for item in value)
    if any(not item or len(item) > 512 for item in result):
        raise ValueError(f"invalid_{name}")
    return result


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


@dataclass(frozen=True, slots=True)
class SupervisorEvent:
    schema: str
    event_id: str
    source_kind: str
    source_ref: str
    event_type: str
    source_revision: str
    reconcile_requested: bool = True
    work_item_authorized: bool = False
    authority_boundary: str = "event_reveals_work_only"


@dataclass(frozen=True, slots=True)
class WorkItem:
    schema: str
    work_item_id: str
    source_kind: str
    source_ref: str
    project_id: str
    employee_id: str
    assignment_id: str
    goal: str
    constraints: tuple[str, ...] = field(default_factory=tuple)
    dependency_refs: tuple[str, ...] = field(default_factory=tuple)
    required_capabilities: tuple[str, ...] = field(default_factory=tuple)
    authority_requirements: tuple[str, ...] = field(default_factory=tuple)
    source_revision: str = ""
    state: str = "open"

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("constraints", "dependency_refs", "required_capabilities", "authority_requirements"):
            value[key] = list(value[key])
        return value


def observe_github_issue_event(*, repository: str, issue_number: int, event_type: str, source_revision: str) -> SupervisorEvent:
    """Issue metadata requests reconciliation; issue prose is not an input here."""
    repo = str(repository or "").strip()
    if not repo or repo.count("/") != 1 or issue_number < 1:
        raise ValueError("invalid_github_issue_ref")
    event_type = str(event_type or "").strip()
    if event_type not in ISSUE_EVENT_TYPES:
        raise ValueError("unsupported_github_issue_event")
    revision = _text(source_revision, "source_revision", 256)
    source_ref = f"github:{repo}#{issue_number}"
    digest = hashlib.sha256(f"{source_ref}\0{event_type}\0{revision}".encode()).hexdigest()[:24]
    return SupervisorEvent(EVENT_SCHEMA, "event_" + digest, "github_issue", source_ref, event_type, revision)


def normalize_work_item(payload: Mapping[str, Any]) -> WorkItem:
    if not isinstance(payload, Mapping):
        raise ValueError("work_item_must_be_object")
    raw = dict(payload)
    if raw.get("schema") != WORK_ITEM_SCHEMA:
        raise ValueError("invalid_work_item_schema")
    extra = sorted(set(raw) - ALLOWED_FIELDS)
    if extra:
        raise ValueError("unexpected_work_item_fields:" + ",".join(extra))
    state = str(raw.get("state") or "open").strip()
    if state not in WORK_ITEM_STATES:
        raise ValueError("invalid_work_item_state")
    source_kind = str(raw.get("source_kind") or "").strip()
    if source_kind not in {"github_issue", "realm_message", "schedule", "user_goal", "canonical_state"}:
        raise ValueError("unsupported_work_item_source")
    deps = tuple(_ref(item, "dependency_ref") for item in _strings(raw.get("dependency_refs"), "dependency_refs"))
    return WorkItem(
        schema=WORK_ITEM_SCHEMA,
        work_item_id=_id(raw.get("work_item_id"), "work_item_id"),
        source_kind=source_kind,
        source_ref=_ref(raw.get("source_ref"), "source_ref"),
        project_id=_id(raw.get("project_id"), "project_id"),
        employee_id=_id(raw.get("employee_id"), "employee_id"),
        assignment_id=_id(raw.get("assignment_id"), "assignment_id"),
        goal=_text(raw.get("goal"), "goal"),
        constraints=_strings(raw.get("constraints"), "constraints"),
        dependency_refs=deps,
        required_capabilities=_strings(raw.get("required_capabilities"), "required_capabilities"),
        authority_requirements=_strings(raw.get("authority_requirements"), "authority_requirements"),
        source_revision=str(raw.get("source_revision") or "").strip(),
        state=state,
    )


class WorkItemStore:
    def __init__(self, runtime: EmployeeRuntime) -> None:
        self.runtime = runtime
        self.root = runtime.root / "supervisor" / "work-items"

    def _path(self, work_item_id: str) -> Path:
        return self.root / f"{_id(work_item_id, 'work_item_id')}.json"

    def get(self, work_item_id: str) -> WorkItem:
        path = self._path(work_item_id)
        if not path.exists():
            raise FileNotFoundError(work_item_id)
        return normalize_work_item(json.loads(path.read_text(encoding="utf-8")))

    def persist(self, payload: Mapping[str, Any]) -> WorkItem:
        item = normalize_work_item(payload)
        path = self._path(item.work_item_id)
        if path.exists():
            existing = self.get(item.work_item_id)
            if existing == item:
                return existing
            raise RuntimeError("work_item_idempotency_conflict")
        _atomic(path, item.as_dict())
        return item

    def project_pending_assignment(self, work_item_id: str):
        item = self.get(work_item_id)
        if item.state != "open":
            raise RuntimeError("work_item_not_open")
        self.runtime.get_employee(item.employee_id)
        try:
            existing = self.runtime.get_assignment(item.assignment_id)
        except FileNotFoundError:
            return self.runtime.create_assignment(
                item.assignment_id, item.employee_id, item.goal, constraints=list(item.constraints)
            )
        if existing.employee_id != item.employee_id or existing.goal != item.goal or tuple(existing.constraints) != item.constraints:
            raise RuntimeError("work_item_assignment_conflict")
        return existing

    def dependencies_ready(self, work_item_id: str, dependency_states: Mapping[str, str]) -> bool:
        item = self.get(work_item_id)
        return all(str(dependency_states.get(ref) or "") == "completed" for ref in item.dependency_refs)

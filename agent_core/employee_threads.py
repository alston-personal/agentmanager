from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.employee_lifecycle import EmployeeLifecycle, RECEIPT_SCHEMA


THREAD_LINK_SCHEMA = "agentos.employee-thread-link/v1"
THREAD_RETURN_SCHEMA = "agentos.employee-thread-return/v1"
RETURNABLE_CHILD_STATES = {"completed", "blocked", "handoff", "cancelled"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _utcnow()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError("unsafe_thread_id")
    return value


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("thread_state_invalid")
    return value


def _link_id(parent_assignment_id: str, child_assignment_id: str) -> str:
    digest = hashlib.sha256(
        f"{parent_assignment_id}\0{child_assignment_id}".encode("utf-8")
    ).hexdigest()[:24]
    return "thread_" + digest


def _return_id(child_assignment_id: str, generation: int) -> str:
    digest = hashlib.sha256(
        f"{child_assignment_id}\0{generation}".encode("utf-8")
    ).hexdigest()[:24]
    return "return_" + digest


@dataclass(slots=True)
class ThreadLink:
    schema: str
    link_id: str
    parent_assignment_id: str
    child_assignment_id: str
    parent_employee_id: str
    child_employee_id: str
    parent_thread_head_at_spawn: str
    status: str
    created_at: str
    return_prepared_at: str | None = None
    applied_at: str | None = None
    applied_parent_thread_head: str | None = None


@dataclass(slots=True)
class ThreadReturnEnvelope:
    schema: str
    return_id: str
    link_id: str
    parent_assignment_id: str
    child_assignment_id: str
    parent_employee_id: str
    child_employee_id: str
    child_outcome: str
    child_thread_head: str
    child_receipt_generation: int
    parent_thread_head_at_spawn: str
    parent_thread_head_current: str
    parent_changed_since_spawn: bool
    prepared_at: str
    apply_authority_required: bool = True
    credential_exposed: bool = False


class EmployeeThreadService:
    """Durable parent/child Cognitive Thread return stack.

    Child completion never mutates the parent thread automatically.  It creates a
    bounded return envelope.  Applying that return requires the parent Employee to
    hold a current live lease and an optimistic thread-head fence, preventing a
    parallel or newer parent continuation from being silently overwritten.
    """

    def __init__(self, lifecycle: EmployeeLifecycle) -> None:
        self.lifecycle = lifecycle
        self.root = lifecycle.root / "threads"
        self.links_dir = self.root / "links"
        self.returns_dir = self.root / "returns"

    def _link_path(self, child_assignment_id: str) -> Path:
        return self.links_dir / f"{_safe_id(child_assignment_id)}.json"

    def _return_path(self, child_assignment_id: str) -> Path:
        return self.returns_dir / f"{_safe_id(child_assignment_id)}.json"

    def get_link(self, child_assignment_id: str) -> ThreadLink | None:
        raw = _read_json(self._link_path(child_assignment_id))
        return ThreadLink(**raw) if raw else None

    def get_return(self, child_assignment_id: str) -> ThreadReturnEnvelope | None:
        raw = _read_json(self._return_path(child_assignment_id))
        return ThreadReturnEnvelope(**raw) if raw else None

    def spawn_child(
        self,
        parent_assignment_id: str,
        parent_lease_id: str,
        child_assignment_id: str,
        child_employee_id: str,
        goal: str,
        *,
        constraints: list[str] | None = None,
        thread_head: str = "",
        now: datetime | None = None,
    ) -> ThreadLink:
        parent_assignment_id = _safe_id(parent_assignment_id)
        child_assignment_id = _safe_id(child_assignment_id)
        child_employee_id = _safe_id(child_employee_id)
        self.lifecycle._require_current_active(  # noqa: SLF001 - same lifecycle boundary
            parent_assignment_id,
            parent_lease_id,
            now=now,
        )
        parent = self.lifecycle.runtime.get_assignment(parent_assignment_id)
        self.lifecycle.runtime.get_employee(child_employee_id)
        link_path = self._link_path(child_assignment_id)
        if link_path.exists():
            raise FileExistsError("thread_link_already_exists")

        self.lifecycle.runtime.create_assignment(
            child_assignment_id,
            child_employee_id,
            goal,
            parent_assignment_id=parent_assignment_id,
            thread_head=str(thread_head or "").strip(),
            constraints=list(constraints or []),
        )
        link = ThreadLink(
            schema=THREAD_LINK_SCHEMA,
            link_id=_link_id(parent_assignment_id, child_assignment_id),
            parent_assignment_id=parent_assignment_id,
            child_assignment_id=child_assignment_id,
            parent_employee_id=parent.employee_id,
            child_employee_id=child_employee_id,
            parent_thread_head_at_spawn=parent.thread_head,
            status="open",
            created_at=_iso(now),
        )
        _atomic_json_write(link_path, asdict(link))
        return link

    def prepare_return(
        self,
        child_assignment_id: str,
        *,
        now: datetime | None = None,
    ) -> ThreadReturnEnvelope:
        child_assignment_id = _safe_id(child_assignment_id)
        link = self.get_link(child_assignment_id)
        if link is None:
            raise FileNotFoundError("thread_link_not_found")
        if link.status == "applied":
            existing = self.get_return(child_assignment_id)
            if existing is None:
                raise RuntimeError("applied_thread_return_missing")
            return existing

        child = self.lifecycle.runtime.get_assignment(child_assignment_id)
        if child.state not in RETURNABLE_CHILD_STATES:
            raise RuntimeError("child_assignment_not_returnable")
        result = child.result if isinstance(child.result, dict) else {}
        if result.get("schema") != RECEIPT_SCHEMA:
            raise RuntimeError("child_terminal_receipt_required")
        generation = int(result.get("generation") or 0)
        if generation < 1:
            raise RuntimeError("child_receipt_generation_invalid")

        receipt_path = self.lifecycle._receipt_path(  # noqa: SLF001
            child_assignment_id, generation
        )
        receipt = _read_json(receipt_path)
        if not receipt or receipt.get("schema") != RECEIPT_SCHEMA:
            raise RuntimeError("child_terminal_receipt_missing")
        if receipt.get("outcome") != child.state:
            raise RuntimeError("child_terminal_receipt_outcome_mismatch")

        parent = self.lifecycle.runtime.get_assignment(link.parent_assignment_id)
        prepared_at = _iso(now)
        envelope = ThreadReturnEnvelope(
            schema=THREAD_RETURN_SCHEMA,
            return_id=_return_id(child_assignment_id, generation),
            link_id=link.link_id,
            parent_assignment_id=link.parent_assignment_id,
            child_assignment_id=child_assignment_id,
            parent_employee_id=link.parent_employee_id,
            child_employee_id=link.child_employee_id,
            child_outcome=child.state,
            child_thread_head=child.thread_head,
            child_receipt_generation=generation,
            parent_thread_head_at_spawn=link.parent_thread_head_at_spawn,
            parent_thread_head_current=parent.thread_head,
            parent_changed_since_spawn=(
                parent.thread_head != link.parent_thread_head_at_spawn
            ),
            prepared_at=prepared_at,
        )
        _atomic_json_write(self._return_path(child_assignment_id), asdict(envelope))
        link.status = "return_ready"
        link.return_prepared_at = prepared_at
        _atomic_json_write(self._link_path(child_assignment_id), asdict(link))
        return envelope

    def apply_return(
        self,
        parent_assignment_id: str,
        parent_lease_id: str,
        child_assignment_id: str,
        *,
        expected_parent_thread_head: str,
        new_parent_thread_head: str,
        now: datetime | None = None,
    ) -> ThreadLink:
        parent_assignment_id = _safe_id(parent_assignment_id)
        child_assignment_id = _safe_id(child_assignment_id)
        link = self.get_link(child_assignment_id)
        if link is None:
            raise FileNotFoundError("thread_link_not_found")
        if link.parent_assignment_id != parent_assignment_id:
            raise PermissionError("thread_parent_mismatch")
        if link.status == "applied":
            if link.applied_parent_thread_head == str(new_parent_thread_head).strip():
                return link
            raise RuntimeError("thread_return_already_applied")
        if link.status != "return_ready":
            raise RuntimeError("thread_return_not_ready")

        envelope = self.get_return(child_assignment_id)
        if envelope is None:
            raise RuntimeError("thread_return_envelope_missing")
        self.lifecycle._require_current_active(  # noqa: SLF001
            parent_assignment_id,
            parent_lease_id,
            now=now,
        )
        parent = self.lifecycle.runtime.get_assignment(parent_assignment_id)
        expected = str(expected_parent_thread_head or "").strip()
        if not expected:
            raise ValueError("expected_parent_thread_head_required")
        if expected != envelope.parent_thread_head_current:
            raise RuntimeError("thread_return_expected_head_mismatch")
        if parent.thread_head != envelope.parent_thread_head_current:
            raise RuntimeError("parent_thread_advanced_after_return_preparation")
        new_head = str(new_parent_thread_head or "").strip()
        if not new_head:
            raise ValueError("new_parent_thread_head_required")

        self.lifecycle.checkpoint(
            parent_assignment_id,
            parent_lease_id,
            new_head,
            now=now,
        )
        link.status = "applied"
        link.applied_at = _iso(now)
        link.applied_parent_thread_head = new_head
        _atomic_json_write(self._link_path(child_assignment_id), asdict(link))
        return link

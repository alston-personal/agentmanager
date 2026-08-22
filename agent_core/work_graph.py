"""Deterministic Work Graph selection for AgentOS continuation.

The planner answers "what should continue next?" from explicit work state,
dependencies and current Project HEAD. It does not execute work or mutate
ProjectState.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from runtime_core.work_v1 import WorkItem, WorkTransition


@dataclass(frozen=True)
class ContinueDecision:
    project_id: str
    head_state_id: str
    work_id: str | None
    reason: str
    stale_base: bool = False


class InMemoryWorkGraph:
    def __init__(self) -> None:
        self._items: dict[str, WorkItem] = {}
        self._transitions: list[WorkTransition] = []

    def add(self, items: Iterable[WorkItem]) -> None:
        staged = list(items)
        ids = {item.work_id for item in staged}
        if len(ids) != len(staged):
            raise ValueError("duplicate WorkItem in batch")
        known = set(self._items) | ids
        for item in staged:
            unknown = [dep for dep in item.depends_on if dep not in known]
            if unknown:
                raise ValueError(f"unknown work dependency: {unknown[0]}")
            if item.work_id in item.depends_on:
                raise ValueError("work cannot depend on itself")
        for item in staged:
            self._items[item.work_id] = item
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(work_id: str) -> None:
            if work_id in visited:
                return
            if work_id in visiting:
                raise ValueError("work dependency cycle detected")
            visiting.add(work_id)
            for dep in self._items[work_id].depends_on:
                visit(dep)
            visiting.remove(work_id)
            visited.add(work_id)

        for work_id in self._items:
            visit(work_id)

    def item(self, work_id: str) -> WorkItem | None:
        return self._items.get(work_id)

    def items(self, project_id: str | None = None) -> tuple[WorkItem, ...]:
        values = self._items.values()
        if project_id is not None:
            values = (item for item in values if item.project_id == project_id)
        return tuple(sorted(values, key=lambda item: item.work_id))

    def transition(self, work_id: str, to_status: str, *, reason: str, actor_ref: str) -> WorkItem:
        current = self._items.get(work_id)
        if current is None:
            raise KeyError(work_id)
        allowed = {
            "pending": {"ready", "blocked", "cancelled"},
            "ready": {"running", "blocked", "cancelled"},
            "running": {"done", "blocked", "ready", "cancelled"},
            "blocked": {"pending", "ready", "cancelled"},
            "done": set(),
            "cancelled": set(),
        }
        if to_status not in allowed[current.status]:
            raise ValueError(f"invalid work transition: {current.status}->{to_status}")
        updated = replace(current, status=to_status)
        self._items.pop(work_id)
        self._items[updated.work_id] = updated
        # WorkItem is content-addressed, so status transition creates a new version.
        self._transitions.append(
            WorkTransition(work_id, current.status, to_status, reason, actor_ref)
        )
        return updated

    def _dependencies_done(self, item: WorkItem) -> bool:
        return all(self._items.get(dep) is not None and self._items[dep].status == "done" for dep in item.depends_on)

    def select_continue(self, *, project_id: str, head_state_id: str) -> ContinueDecision:
        """Choose one deterministic next item without mutating graph state."""
        candidates: list[WorkItem] = []
        for item in self.items(project_id):
            if item.status not in {"pending", "ready"}:
                continue
            if not self._dependencies_done(item):
                continue
            candidates.append(item)
        if not candidates:
            return ContinueDecision(project_id, head_state_id, None, "no_ready_work")

        # Prefer exact HEAD work; stale work is still visible but never silently
        # treated as current. Within the same base, higher priority wins, then ID.
        candidates.sort(
            key=lambda item: (
                item.base_state_id != head_state_id,
                -item.priority,
                item.work_id,
            )
        )
        chosen = candidates[0]
        stale = chosen.base_state_id != head_state_id
        return ContinueDecision(
            project_id=project_id,
            head_state_id=head_state_id,
            work_id=chosen.work_id,
            reason="stale_base_requires_rebase_or_validation" if stale else "highest_priority_ready_at_head",
            stale_base=stale,
        )

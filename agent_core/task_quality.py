"""Fail-closed quality contract for executable AgentOS tasks."""

from __future__ import annotations

from dataclasses import dataclass
import re


PLACEHOLDER_TASKS = frozenset({
    "define objectives", "break work into milestones",
    "execute and report progress", "implementation", "review",
})
_GENERIC_PREFIXES = (
    "define objectives", "break work into milestones", "execute and report progress",
)
_FIELD_RE = re.compile(
    r"(?:^|\s*\|\s*)(workspace|acceptance|prerequisite)\s*=\s*([^|]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TaskContract:
    description: str
    workspace: str
    acceptance: str
    prerequisite: str | None = None


class TaskQualityError(ValueError):
    """The task cannot be persisted or executed."""


def parse_task_contract(task_text: str) -> TaskContract:
    text = " ".join(str(task_text or "").strip().split())
    if not text:
        raise TaskQualityError("task description is empty")
    description = text.split("|", 1)[0].strip()
    normalized_description = re.sub(r"^(?:\[[^]]+\]\s*)+", "", description).casefold()
    if (
        normalized_description in PLACEHOLDER_TASKS
        or any(
            normalized_description == phrase or normalized_description.startswith(phrase + " ")
            for phrase in _GENERIC_PREFIXES
        )
    ):
        raise TaskQualityError(f"placeholder task is forbidden: {description}")
    if len(description) < 12:
        raise TaskQualityError("task description lacks an actionable scope")
    fields = {key.casefold(): value.strip() for key, value in _FIELD_RE.findall(text)}
    workspace = fields.get("workspace", "")
    acceptance = fields.get("acceptance", "")
    if not workspace:
        raise TaskQualityError("task must declare workspace=<path-or-repo>")
    if len(workspace) < 3:
        raise TaskQualityError("workspace is not specific enough")
    if not acceptance:
        raise TaskQualityError("task must declare acceptance=<command-or-evidence>")
    if len(acceptance) < 8:
        raise TaskQualityError("acceptance condition is not specific enough")
    return TaskContract(description, workspace, acceptance, fields.get("prerequisite") or None)


def validate_task_text(task_text: str) -> str:
    parse_task_contract(task_text)
    return " ".join(str(task_text).strip().split())


def is_executable_task(task_text: str) -> bool:
    try:
        validate_task_text(task_text)
    except TaskQualityError:
        return False
    return True

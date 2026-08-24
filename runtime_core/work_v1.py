"""Portable Work Graph IR for deterministic AgentOS continuation.

Work is separate from canonical ProjectState. A WorkItem describes an intended
unit of progress against a specific base state and may be selected/executed by
many interchangeable runtimes without making any runtime the project authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


WORK_SCHEMA = "agentos.work/v1"
WORK_STATUSES = frozenset({"pending", "ready", "running", "blocked", "done", "cancelled"})


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class WorkItem:
    project_id: str
    base_state_id: str
    instruction: str
    capability: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    priority: int = 0
    status: str = "pending"
    acceptance_criteria: tuple[str, ...] = field(default_factory=tuple)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    provider_policy: dict[str, Any] = field(default_factory=dict)
    created_by: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = WORK_SCHEMA

    def __post_init__(self) -> None:
        if not self.project_id.strip() or not self.base_state_id.strip():
            raise ValueError("project_id and base_state_id are required")
        if not self.instruction.strip() or not self.capability.strip():
            raise ValueError("instruction and capability are required")
        if self.status not in WORK_STATUSES:
            raise ValueError("invalid work status")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on must be unique")
        if any(not str(item).strip() for item in self.acceptance_criteria):
            raise ValueError("acceptance criteria cannot be blank")

    def identity_payload(self) -> dict[str, Any]:
        """Fields that define the stable identity of a unit of intended work.

        Lifecycle state deliberately does not participate. A work item must keep
        the same ID while moving pending -> ready -> running -> done so dependency
        edges remain stable. Mutable scheduling annotations belong to the graph,
        not identity.
        """
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "base_state_id": self.base_state_id,
            "instruction": self.instruction,
            "capability": self.capability,
            "depends_on": self.depends_on,
            "acceptance_criteria": self.acceptance_criteria,
            "runtime_policy": self.runtime_policy,
            "provider_policy": self.provider_policy,
            "created_by": self.created_by,
            "metadata": self.metadata,
        }

    @property
    def work_id(self) -> str:
        return "work_" + sha256(_canonical(self.identity_payload()).encode("utf-8")).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["work_id"] = self.work_id
        return value


@dataclass(frozen=True)
class WorkTransition:
    work_id: str
    from_status: str
    to_status: str
    reason: str
    actor_ref: str

    def __post_init__(self) -> None:
        if self.from_status not in WORK_STATUSES or self.to_status not in WORK_STATUSES:
            raise ValueError("invalid transition status")
        if not self.work_id.strip() or not self.reason.strip() or not self.actor_ref.strip():
            raise ValueError("work_id, reason and actor_ref are required")

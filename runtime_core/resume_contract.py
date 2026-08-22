"""Resume contract for restoring goal-directed execution across sessions/providers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

SCHEMA_VERSION = "agentos.resume-contract/v1"
ACTIVE_STATES = {"EXECUTING", "WAITING_EXTERNAL", "BLOCKED_RECOVERABLE"}
TERMINAL_STATES = {"DONE", "BLOCKED_HUMAN_AUTHORITY", "FAILED_TERMINAL"}

@dataclass(frozen=True)
class ResumeContract:
    project_id: str
    goal: str
    execution_state: str
    current_step: str
    next_action: str
    terminal_conditions: List[str] = field(default_factory=lambda: ["DONE", "BLOCKED_HUMAN_AUTHORITY", "FAILED_TERMINAL"])
    preferred_execution_path: List[str] = field(default_factory=list)
    capability_bindings: List[str] = field(default_factory=list)
    last_success: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.execution_state not in ACTIVE_STATES | TERMINAL_STATES:
            raise ValueError(f"unsupported execution_state: {self.execution_state}")
        if not self.project_id or not self.goal:
            raise ValueError("project_id and goal are required")
        if self.execution_state in ACTIVE_STATES and (not self.current_step or not self.next_action):
            raise ValueError("active resume contract requires current_step and next_action")

    @property
    def should_continue(self) -> bool:
        return self.execution_state in ACTIVE_STATES

    @property
    def requires_human(self) -> bool:
        return self.execution_state == "BLOCKED_HUMAN_AUTHORITY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResumeContract":
        if data.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValueError(f"unsupported Resume Contract schema: {data.get('schema_version')}")
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in allowed})


def restore_execution_disposition(continuation: Dict[str, Any]) -> ResumeContract | None:
    """Recover the durable execution disposition embedded in an IR continuation."""
    raw = continuation.get("resume_contract") if isinstance(continuation, dict) else None
    if not isinstance(raw, dict):
        return None
    return ResumeContract.from_dict(raw)

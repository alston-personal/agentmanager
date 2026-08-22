"""Durable goal execution state machine independent of any chat session.

The controller deliberately separates WAITING_EXTERNAL from human blocking:
waiting is an execution state, not permission to yield the goal back to a user.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

SCHEMA_VERSION = "agentos.goal-controller/v1"
ACTIVE = frozenset({"READY", "EXECUTING", "WAITING_EXTERNAL", "BLOCKED_RECOVERABLE"})
TERMINAL = frozenset({"DONE", "BLOCKED_HUMAN_AUTHORITY", "FAILED_TERMINAL", "CANCELLED"})
ALL_STATES = ACTIVE | TERMINAL


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GoalControllerState:
    goal_id: str
    project_id: str
    goal: str
    revision: int
    execution_state: str
    lease_owner: str
    lease_epoch: int
    next_action: str
    capability_manifest_digest: str
    execution_environment_fingerprint: str
    last_receipt: dict[str, Any] = field(default_factory=dict)
    failure_refs: tuple[str, ...] = field(default_factory=tuple)
    safety_constraints: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.execution_state not in ALL_STATES:
            raise ValueError(f"invalid execution_state: {self.execution_state}")
        if self.revision < 1 or self.lease_epoch < 1:
            raise ValueError("revision and lease_epoch must be positive")
        if not all((self.goal_id, self.project_id, self.goal, self.lease_owner)):
            raise ValueError("goal identity and lease owner are required")
        if self.execution_state in ACTIVE and not self.next_action:
            raise ValueError("active goal requires next_action")

    @property
    def terminal(self) -> bool:
        return self.execution_state in TERMINAL

    @property
    def should_continue(self) -> bool:
        return self.execution_state in ACTIVE

    @property
    def may_yield_to_human(self) -> bool:
        return self.execution_state in {"DONE", "BLOCKED_HUMAN_AUTHORITY", "FAILED_TERMINAL", "CANCELLED"}

    @property
    def state_digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_digest:
            value["state_digest"] = _digest(value)
        return value

    def assert_executor(self, *, executor_id: str, observed_revision: int, observed_lease_epoch: int) -> None:
        """Fail closed before effects when a session/runtime is stale."""
        if executor_id != self.lease_owner:
            raise PermissionError("STALE_EXECUTOR: lease owner changed")
        if observed_revision != self.revision:
            raise PermissionError("STALE_EXECUTOR: goal revision changed")
        if observed_lease_epoch != self.lease_epoch:
            raise PermissionError("STALE_EXECUTOR: lease epoch changed")

    def transition(self, *, new_state: str, next_action: str, receipt: dict[str, Any] | None = None) -> "GoalControllerState":
        if self.terminal:
            raise ValueError("terminal goal cannot transition without explicit new revision")
        if new_state not in ALL_STATES:
            raise ValueError(f"invalid execution_state: {new_state}")
        return GoalControllerState(
            goal_id=self.goal_id,
            project_id=self.project_id,
            goal=self.goal,
            revision=self.revision + 1,
            execution_state=new_state,
            lease_owner=self.lease_owner,
            lease_epoch=self.lease_epoch,
            next_action=next_action,
            capability_manifest_digest=self.capability_manifest_digest,
            execution_environment_fingerprint=self.execution_environment_fingerprint,
            last_receipt=receipt or self.last_receipt,
            failure_refs=self.failure_refs,
            safety_constraints=self.safety_constraints,
        )

"""Durable goal execution state machine independent of any chat session.

Context is cache, not canonical state. WAITING_EXTERNAL remains active work and
must not be treated as permission to yield a goal back to a human.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
from typing import Any

SCHEMA_VERSION = "agentos.goal-controller/v2"
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
    repository: str
    canonical_ref: str
    observed_head_sha: str
    last_receipt: dict[str, Any] = field(default_factory=dict)
    failure_refs: tuple[str, ...] = field(default_factory=tuple)
    safety_constraints: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.execution_state not in ALL_STATES:
            raise ValueError(f"invalid execution_state: {self.execution_state}")
        if self.revision < 1 or self.lease_epoch < 1:
            raise ValueError("revision and lease_epoch must be positive")
        required = (self.goal_id, self.project_id, self.goal, self.lease_owner, self.repository, self.canonical_ref, self.observed_head_sha)
        if any(not str(value).strip() for value in required):
            raise ValueError("goal identity, lease owner and canonical git coordinates are required")
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
        return self.execution_state in TERMINAL

    @property
    def state_digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if include_digest:
            value["state_digest"] = _digest(value)
        return value

    def assert_executor(self, *, executor_id: str, observed_revision: int, observed_lease_epoch: int, repository: str, canonical_ref: str, current_head_sha: str) -> None:
        """Fail closed before effects when ownership or canonical code state drifted."""
        if executor_id != self.lease_owner:
            raise PermissionError("STALE_EXECUTOR: lease owner changed")
        if observed_revision != self.revision:
            raise PermissionError("STALE_EXECUTOR: goal revision changed")
        if observed_lease_epoch != self.lease_epoch:
            raise PermissionError("STALE_EXECUTOR: lease epoch changed")
        if repository != self.repository or canonical_ref != self.canonical_ref:
            raise PermissionError("STALE_EXECUTOR: canonical repository/ref changed")
        if current_head_sha != self.observed_head_sha:
            raise PermissionError("STALE_EXECUTOR: canonical HEAD changed; reconcile before effect")

    def reconcile_head(self, *, current_head_sha: str, next_action: str | None = None) -> "GoalControllerState":
        """Advance the observation boundary without changing execution ownership."""
        if not current_head_sha:
            raise ValueError("current_head_sha is required")
        return replace(
            self,
            revision=self.revision + 1,
            observed_head_sha=current_head_sha,
            next_action=next_action or self.next_action,
        )

    def transition(self, *, new_state: str, next_action: str, receipt: dict[str, Any] | None = None) -> "GoalControllerState":
        if self.terminal:
            raise ValueError("terminal goal cannot transition without explicit new revision")
        if new_state not in ALL_STATES:
            raise ValueError(f"invalid execution_state: {new_state}")
        return replace(
            self,
            revision=self.revision + 1,
            execution_state=new_state,
            next_action=next_action,
            last_receipt=receipt or self.last_receipt,
        )

"""Portable intent/approval contracts for AgentOS governance.

Capability risk evaluation remains authoritative in ``agent_core.governance``.
This module only carries runtime-neutral intent and approval envelopes so nodes,
providers and executors can bind effects to a governed decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


GOVERNANCE_SCHEMA = "agentos.governance/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ActionIntent:
    realm_id: str
    project_id: str
    actor_ref: str
    capability: str
    target_ref: str
    operation: str
    requested_level: int
    idempotency_key: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = GOVERNANCE_SCHEMA

    def __post_init__(self) -> None:
        required = (
            self.realm_id,
            self.project_id,
            self.actor_ref,
            self.capability,
            self.target_ref,
            self.operation,
            self.idempotency_key,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("intent identity fields are required")
        if self.requested_level not in range(0, 7):
            raise ValueError("requested_level must be 0..6")

    @property
    def intent_id(self) -> str:
        return "intent_" + sha256(_canonical(asdict(self)).encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class ApprovalGrant:
    intent_id: str
    approver_ref: str
    scope: str
    expires_at: str | None = None
    grant_id: str = ""

    def __post_init__(self) -> None:
        if not self.intent_id.strip() or not self.approver_ref.strip() or not self.scope.strip():
            raise ValueError("approval identity fields are required")

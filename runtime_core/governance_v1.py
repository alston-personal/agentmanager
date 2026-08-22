"""Portable governance contracts for AgentOS.

Governance is an independent authority layer.  A runtime/model/provider may
propose an intent, but it cannot grant itself permission to execute it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


GOVERNANCE_SCHEMA = "agentos.governance/v1"
CAPABILITY_LEVELS = {
    "observe": 0,
    "synthesize": 1,
    "propose": 2,
    "commit": 3,
    "act": 4,
    "high_impact": 5,
    "autonomous": 6,
}
RISK_BANDS = frozenset({"low", "medium", "high", "critical"})
DECISIONS = frozenset({"allow", "deny", "require_approval", "proposal_only"})


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class CapabilityProfile:
    capability: str
    level: int
    risk_band: str
    read_scopes: tuple[str, ...] = field(default_factory=tuple)
    write_scopes: tuple[str, ...] = field(default_factory=tuple)
    external_effect: bool = False
    physical_effect: bool = False
    reversible: bool = True
    autonomous: bool = False
    cross_realm: bool = False
    controls: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = GOVERNANCE_SCHEMA

    def __post_init__(self) -> None:
        if not self.capability.strip():
            raise ValueError("capability is required")
        if self.level not in range(0, 7):
            raise ValueError("capability level must be 0..6")
        if self.risk_band not in RISK_BANDS:
            raise ValueError("invalid risk band")
        if self.physical_effect and not self.external_effect:
            raise ValueError("physical effect implies external effect")
        if self.autonomous and self.level < CAPABILITY_LEVELS["autonomous"]:
            raise ValueError("autonomous capability must be level 6")
        if self.cross_realm:
            raise ValueError("cross-realm authority is forbidden by default")


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
        required = (self.realm_id, self.project_id, self.actor_ref, self.capability, self.target_ref, self.operation, self.idempotency_key)
        if any(not str(value).strip() for value in required):
            raise ValueError("intent identity fields are required")
        if self.requested_level not in range(0, 7):
            raise ValueError("requested_level must be 0..6")

    @property
    def intent_id(self) -> str:
        payload = asdict(self)
        return "intent_" + sha256(_canonical(payload).encode("utf-8")).hexdigest()[:32]


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
        if self.grant_id and not self.grant_id.strip():
            raise ValueError("invalid grant_id")


@dataclass(frozen=True)
class GovernanceDecision:
    intent_id: str
    decision: str
    reason: str
    effective_level: int
    required_controls: tuple[str, ...] = field(default_factory=tuple)
    missing_controls: tuple[str, ...] = field(default_factory=tuple)
    approval_required: bool = False
    audit_tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError("invalid governance decision")
        if not self.intent_id.strip() or not self.reason.strip():
            raise ValueError("decision intent_id/reason are required")
        if self.effective_level not in range(0, 7):
            raise ValueError("effective_level must be 0..6")

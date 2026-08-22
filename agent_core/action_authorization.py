"""Bind canonical governance decisions to concrete action intents.

High-impact approvals are intent-scoped, and capability profiles are resolved
only from the authoritative GovernanceRegistry. Runtimes/providers/nodes may
name a capability but cannot supply their own permissions or controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agent_core.governance import CapabilityLevel, GovernanceDecision, GovernanceGate
from agent_core.governance_registry import GovernanceRegistry
from runtime_core.governance_v1 import ActionIntent, ApprovalGrant


@dataclass(frozen=True)
class ActionAuthorization:
    intent_id: str
    capability: str
    effective_level: CapabilityLevel
    allowed: bool
    reason: str
    approval_ref: str | None = None


def _approval_valid(intent: ActionIntent, approval: ApprovalGrant | None) -> bool:
    if approval is None or approval.intent_id != intent.intent_id:
        return False
    if approval.scope not in {intent.capability, "*"}:
        return False
    if approval.expires_at:
        try:
            expires = datetime.fromisoformat(approval.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return False
    return True


class ActionAuthorizationGate:
    def __init__(
        self,
        registry: GovernanceRegistry,
        capability_gate: GovernanceGate | None = None,
    ) -> None:
        self._registry = registry
        self._capability_gate = capability_gate or GovernanceGate()

    def evaluate(
        self,
        *,
        intent: ActionIntent,
        approval: ApprovalGrant | None = None,
    ) -> ActionAuthorization:
        profile = self._registry.get(intent.capability)
        if profile is None:
            return ActionAuthorization(
                intent.intent_id,
                intent.capability,
                CapabilityLevel.OBSERVE,
                False,
                "unknown capability; fail closed",
            )
        if intent.requested_level > int(profile.declared_level):
            return ActionAuthorization(
                intent.intent_id,
                intent.capability,
                profile.declared_level,
                False,
                "requested authority exceeds declared capability",
            )

        decision: GovernanceDecision = self._capability_gate.evaluate(
            profile,
            requested_level=intent.requested_level,
        )
        if not decision.allowed:
            return ActionAuthorization(
                intent.intent_id,
                intent.capability,
                decision.effective_level,
                False,
                decision.reason,
            )

        approval_required = (
            decision.effective_level >= CapabilityLevel.HIGH_IMPACT
            or "external_high_impact" in profile.effects
        )
        if approval_required and not _approval_valid(intent, approval):
            return ActionAuthorization(
                intent.intent_id,
                intent.capability,
                CapabilityLevel.PROPOSE,
                False,
                "intent-bound owner approval required",
            )

        return ActionAuthorization(
            intent.intent_id,
            intent.capability,
            decision.effective_level,
            True,
            "intent authorized",
            approval_ref=(approval.grant_id or approval.approver_ref) if approval else None,
        )

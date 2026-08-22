"""Executable governance gate for AgentOS capability intents."""

from __future__ import annotations

from datetime import datetime, timezone

from runtime_core.governance_v1 import (
    ActionIntent,
    ApprovalGrant,
    CapabilityProfile,
    GovernanceDecision,
)


LEVEL_CONTROLS: dict[int, frozenset[str]] = {
    0: frozenset({"authentication", "provenance"}),
    1: frozenset({"authentication", "provenance", "confidence", "contradiction_retention"}),
    2: frozenset({"authentication", "provenance", "typed_proposal", "validation", "reviewability"}),
    3: frozenset({"authentication", "provenance", "scoped_principal", "audit", "rollback_or_supersession"}),
    4: frozenset({"authentication", "provenance", "scoped_principal", "audit", "idempotency", "receipt", "bounded_scope", "compensation"}),
    5: frozenset({"authentication", "provenance", "scoped_principal", "audit", "idempotency", "receipt", "bounded_scope", "compensation", "approval_gate", "circuit_breaker", "minimal_privilege"}),
    6: frozenset({"authentication", "provenance", "scoped_principal", "audit", "idempotency", "receipt", "bounded_scope", "compensation", "approval_gate", "circuit_breaker", "minimal_privilege", "budget", "anomaly_detection", "revocation", "human_override", "independent_verification"}),
}


def required_controls(profile: CapabilityProfile) -> frozenset[str]:
    required = set(LEVEL_CONTROLS[profile.level])
    if not profile.reversible and profile.level >= 3:
        required.add("explicit_recovery_plan")
    if profile.external_effect:
        required.update({"side_effect_ledger", "idempotency", "receipt"})
    if profile.physical_effect:
        required.update({"physical_safety_policy", "circuit_breaker"})
    if profile.autonomous:
        required.update({"budget", "anomaly_detection", "revocation", "human_override"})
    return frozenset(required)


def missing_governance(profile: CapabilityProfile) -> tuple[str, ...]:
    return tuple(sorted(required_controls(profile) - profile.controls))


def capability_is_release_ready(profile: CapabilityProfile) -> bool:
    return not missing_governance(profile)


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


class GovernanceGate:
    """Deterministic fail-closed authorization boundary.

    The gate never executes the intent. It only decides the maximum authority
    that may proceed to the appropriate State/Cognition/SideEffect executor.
    """

    def evaluate(
        self,
        *,
        intent: ActionIntent,
        profile: CapabilityProfile | None,
        approval: ApprovalGrant | None = None,
    ) -> GovernanceDecision:
        if profile is None:
            return GovernanceDecision(intent.intent_id, "deny", "unknown_capability", 0)
        if profile.capability != intent.capability:
            return GovernanceDecision(intent.intent_id, "deny", "capability_profile_mismatch", 0)
        if intent.requested_level > profile.level:
            return GovernanceDecision(intent.intent_id, "deny", "requested_authority_exceeds_profile", profile.level)

        missing = missing_governance(profile)
        if missing:
            # Missing controls never grant the requested authority. Cognitive/
            # planning levels can degrade to proposal-only; mutation/action
            # levels deny outright.
            decision = "proposal_only" if intent.requested_level <= 2 else "deny"
            return GovernanceDecision(
                intent.intent_id,
                decision,
                "governance_controls_incomplete",
                min(intent.requested_level, 2),
                tuple(sorted(required_controls(profile))),
                missing,
                approval_required=False,
                audit_tags=("fail_closed",),
            )

        approval_needed = profile.level >= 5 or profile.risk_band in {"high", "critical"} or profile.physical_effect
        if approval_needed and not _approval_valid(intent, approval):
            return GovernanceDecision(
                intent.intent_id,
                "require_approval",
                "explicit_approval_required",
                min(intent.requested_level, 2),
                tuple(sorted(required_controls(profile))),
                approval_required=True,
                audit_tags=("approval_gate",),
            )

        return GovernanceDecision(
            intent.intent_id,
            "allow",
            "governance_satisfied",
            intent.requested_level,
            tuple(sorted(required_controls(profile))),
            approval_required=approval_needed,
            audit_tags=("authorized",),
        )


def governance_change_allowed(*, old_level: int, new_level: int, owner_approved: bool) -> bool:
    """Governance may tighten itself, but cannot self-grant greater authority."""
    if new_level <= old_level:
        return True
    return owner_approved

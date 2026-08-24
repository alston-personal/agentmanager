"""Governance-owned Node revocation.

Revocation must work even when the Node is offline or uncooperative. A revoked
Node may not self-reactivate through reconnect/onboarding.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.node_directory_store import NodeDirectoryStore
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


@dataclass(frozen=True)
class NodeRevocationReceipt:
    node_id: str
    actor_ref: str
    governance_ref: str
    reason: str
    checkpoint_id: str


class NodeRevocationService:
    def __init__(self, directory: NodeDirectoryStore) -> None:
        self.directory = directory

    def revoke(
        self,
        node_id: str,
        *,
        actor_ref: str,
        governance_ref: str,
        reason: str,
        observed_at: str,
    ) -> NodeRevocationReceipt:
        if not actor_ref.strip() or not governance_ref.strip() or not reason.strip():
            raise ValueError("actor_ref, governance_ref and reason are required")
        current = self.directory.checkpoint(node_id)
        if current is None:
            raise KeyError(f"unknown Node: {node_id}")
        if current.lifecycle is NodeLifecycle.REVOKED:
            raise ValueError("Node is already revoked")
        revoked = OnboardingCheckpoint(
            node_id=node_id,
            lifecycle=NodeLifecycle.REVOKED,
            observed_at=observed_at,
            identity_id=current.identity_id,
            capability_manifest_id=current.capability_manifest_id,
            reconciliation_plan_id=current.reconciliation_plan_id,
            governance_ref=governance_ref,
        )
        self.directory.advance(revoked)
        return NodeRevocationReceipt(
            node_id=node_id,
            actor_ref=actor_ref,
            governance_ref=governance_ref,
            reason=reason,
            checkpoint_id=revoked.checkpoint_id,
        )

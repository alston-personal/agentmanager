"""Governed Node onboarding coordinator.

This module closes the semantic gap between enrollment, capability discovery,
reconciliation, governance registration and activation.  It deliberately does
not create governance profiles on behalf of a Node.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_core.governance_registry import GovernanceRegistry
from agent_core.node_registry import NodeRegistry
from runtime_core.node_v1 import NodeCapabilityManifest
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint, validate_transition


@dataclass(frozen=True)
class GovernanceGap:
    capability: str
    reason: str


@dataclass(frozen=True)
class OnboardingAssessment:
    node_id: str
    lifecycle: NodeLifecycle
    governance_gaps: tuple[GovernanceGap, ...]
    can_activate: bool


class NodeOnboardingCoordinator:
    def __init__(self, *, nodes: NodeRegistry, governance: GovernanceRegistry) -> None:
        self.nodes = nodes
        self.governance = governance

    def register_discovery(self, manifest: NodeCapabilityManifest) -> str:
        """Record discovered capability metadata only; no authorization is inferred."""
        return self.nodes.register_manifest(manifest)

    def assess_governance(self, node_id: str) -> OnboardingAssessment:
        manifest = self.nodes.manifest(node_id)
        if manifest is None:
            raise KeyError(f"unknown Node: {node_id}")
        gaps = tuple(
            GovernanceGap(item.capability, "no governance-owned profile registered")
            for item in manifest.capabilities
            if self.governance.get(item.capability) is None
        )
        return OnboardingAssessment(
            node_id=node_id,
            lifecycle=NodeLifecycle.GOVERNED if not gaps else NodeLifecycle.REGISTERED,
            governance_gaps=gaps,
            can_activate=not gaps,
        )

    def advance(self, checkpoint: OnboardingCheckpoint, target: NodeLifecycle, *, governance_ref: str | None = None) -> OnboardingCheckpoint:
        validate_transition(checkpoint.lifecycle, target)
        if target is NodeLifecycle.GOVERNED:
            assessment = self.assess_governance(checkpoint.node_id)
            if not assessment.can_activate:
                names = ", ".join(gap.capability for gap in assessment.governance_gaps)
                raise PermissionError(f"Node has ungoverned capabilities: {names}")
            if not governance_ref:
                raise ValueError("governance_ref is required for GOVERNED checkpoint")
        if target is NodeLifecycle.ACTIVE:
            if checkpoint.lifecycle is not NodeLifecycle.GOVERNED or not checkpoint.governance_ref:
                raise PermissionError("Node cannot activate without a governed checkpoint")

        return OnboardingCheckpoint(
            node_id=checkpoint.node_id,
            lifecycle=target,
            observed_at=checkpoint.observed_at,
            identity_id=checkpoint.identity_id,
            capability_manifest_id=checkpoint.capability_manifest_id,
            reconciliation_plan_id=checkpoint.reconciliation_plan_id,
            governance_ref=governance_ref or checkpoint.governance_ref,
        )

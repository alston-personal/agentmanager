"""End-to-end AgentOS Node onboarding and reconnect pipeline.

The pipeline composes identity claim, capability discovery, cognitive
reconciliation, durable registration and governance assessment. It may activate
only when a governance-owned profile exists for every reported capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agent_core.enrollment_service import EnrollmentReceipt
from agent_core.node_directory_store import NodeDirectoryStore
from agent_core.node_onboarding import NodeOnboardingCoordinator, OnboardingAssessment
from agent_core.node_reconciliation import LocalCognitionDescriptor, NodeReconciliationPlan, plan_node_reconciliation
from runtime_core.node_v1 import NodeCapabilityDelta, NodeCapabilityManifest, diff_manifests
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


@dataclass(frozen=True)
class OnboardingPipelineResult:
    checkpoint: OnboardingCheckpoint
    reconciliation: NodeReconciliationPlan
    governance: OnboardingAssessment
    capability_delta: NodeCapabilityDelta | None = None


class NodeOnboardingPipeline:
    def __init__(
        self,
        *,
        directory: NodeDirectoryStore,
        coordinator: NodeOnboardingCoordinator,
    ) -> None:
        self.directory = directory
        self.coordinator = coordinator

    def ingest(
        self,
        *,
        receipt: EnrollmentReceipt,
        manifest: NodeCapabilityManifest,
        local_cognition: Iterable[LocalCognitionDescriptor] = (),
        known_hashes: set[str] | None = None,
        contradicted_hashes: set[str] | None = None,
        governance_ref: str | None = None,
    ) -> OnboardingPipelineResult:
        if manifest.identity != receipt.node_identity:
            raise ValueError("capability manifest identity does not match enrollment receipt")

        existing_checkpoint = self.directory.checkpoint(receipt.node_identity.node_id)
        previous_manifest = self.directory.latest_manifest(receipt.node_identity.node_id)
        capability_delta = diff_manifests(previous_manifest, manifest) if previous_manifest else None

        if existing_checkpoint is None:
            self.directory.initialize_node(receipt.checkpoint)
        elif existing_checkpoint.lifecycle is NodeLifecycle.REVOKED:
            raise PermissionError("revoked Node cannot re-onboard itself")

        self.directory.save_manifest(manifest)
        self.coordinator.register_discovery(manifest)

        discovered = OnboardingCheckpoint(
            node_id=manifest.identity.node_id,
            lifecycle=NodeLifecycle.DISCOVERED,
            observed_at=manifest.observed_at,
            identity_id=manifest.identity.identity_id,
            capability_manifest_id=manifest.manifest_id,
        )
        self.directory.advance(discovered)

        reconciliation = plan_node_reconciliation(
            node_id=manifest.identity.node_id,
            observed_at=manifest.observed_at,
            local_items=local_cognition,
            known_hashes=known_hashes or set(),
            contradicted_hashes=contradicted_hashes,
        )
        reconciled = OnboardingCheckpoint(
            node_id=manifest.identity.node_id,
            lifecycle=NodeLifecycle.RECONCILED,
            observed_at=manifest.observed_at,
            identity_id=manifest.identity.identity_id,
            capability_manifest_id=manifest.manifest_id,
            reconciliation_plan_id=reconciliation.plan_id,
        )
        self.directory.advance(reconciled)

        registered = OnboardingCheckpoint(
            node_id=manifest.identity.node_id,
            lifecycle=NodeLifecycle.REGISTERED,
            observed_at=manifest.observed_at,
            identity_id=manifest.identity.identity_id,
            capability_manifest_id=manifest.manifest_id,
            reconciliation_plan_id=reconciliation.plan_id,
        )
        self.directory.advance(registered)

        assessment = self.coordinator.assess_governance(manifest.identity.node_id)
        checkpoint = registered
        if assessment.can_activate and governance_ref:
            governed = self.coordinator.advance(registered, NodeLifecycle.GOVERNED, governance_ref=governance_ref)
            self.directory.advance(governed)
            checkpoint = self.coordinator.advance(governed, NodeLifecycle.ACTIVE)
            self.directory.advance(checkpoint)

        return OnboardingPipelineResult(
            checkpoint=checkpoint,
            reconciliation=reconciliation,
            governance=assessment,
            capability_delta=capability_delta,
        )

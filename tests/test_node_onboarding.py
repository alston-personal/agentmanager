import pytest

from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel, RiskDimensions
from agent_core.governance_registry import GovernanceRegistry
from agent_core.node_onboarding import NodeOnboardingCoordinator
from agent_core.node_registry import NodeRegistry
from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest, NodeIdentity
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


def _manifest() -> NodeCapabilityManifest:
    return NodeCapabilityManifest(
        identity=NodeIdentity("node-a", "realm-personal", "node-a", "linux", "aarch64"),
        observed_at="2026-08-22T09:00:00Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )


def test_node_cannot_become_governed_while_capability_has_no_profile() -> None:
    nodes = NodeRegistry()
    governance = GovernanceRegistry()
    coordinator = NodeOnboardingCoordinator(nodes=nodes, governance=governance)
    manifest = _manifest()
    coordinator.register_discovery(manifest)

    assessment = coordinator.assess_governance("node-a")
    assert assessment.can_activate is False
    assert assessment.governance_gaps[0].capability == "camera.observe"

    checkpoint = OnboardingCheckpoint(
        node_id="node-a",
        lifecycle=NodeLifecycle.REGISTERED,
        observed_at=manifest.observed_at,
        identity_id=manifest.identity.identity_id,
        capability_manifest_id=manifest.manifest_id,
    )
    with pytest.raises(PermissionError, match="ungoverned capabilities"):
        coordinator.advance(checkpoint, NodeLifecycle.GOVERNED, governance_ref="gov-test")


def test_node_activation_requires_governance_owned_profile_and_checkpoint() -> None:
    profile = CapabilityGovernanceProfile.build(
        "camera.observe",
        CapabilityLevel.OBSERVE,
        risks=RiskDimensions(authority=0, autonomy=0),
    )
    governance = GovernanceRegistry((profile,))
    nodes = NodeRegistry()
    coordinator = NodeOnboardingCoordinator(nodes=nodes, governance=governance)
    manifest = _manifest()
    coordinator.register_discovery(manifest)

    registered = OnboardingCheckpoint(
        node_id="node-a",
        lifecycle=NodeLifecycle.REGISTERED,
        observed_at=manifest.observed_at,
        identity_id=manifest.identity.identity_id,
        capability_manifest_id=manifest.manifest_id,
    )
    governed = coordinator.advance(registered, NodeLifecycle.GOVERNED, governance_ref="gov-camera-observe")
    active = coordinator.advance(governed, NodeLifecycle.ACTIVE)
    assert active.lifecycle is NodeLifecycle.ACTIVE
    assert active.governance_ref == "gov-camera-observe"

from datetime import datetime, timezone

import pytest

from agent_core.enrollment_service import EnrollmentService
from agent_core.enrollment_store import EnrollmentStore
from agent_core.governance import CapabilityGovernanceProfile, CapabilityLevel, RiskDimensions
from agent_core.governance_registry import GovernanceRegistry
from agent_core.node_directory_store import NodeDirectoryStore
from agent_core.node_onboarding import NodeOnboardingCoordinator
from agent_core.node_registry import NodeRegistry
from agent_core.node_revocation import NodeRevocationService
from agent_core.onboarding_pipeline import NodeOnboardingPipeline
from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinTicket, NodeLifecycle


def _receipt(tmp_path):
    store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
    )
    envelope, secret = store.issue(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
    )
    claim = EnrollmentClaim(
        enrollment_id=envelope.enrollment_id,
        node_public_key="ssh-ed25519 AAAATEST agentos-node",
        device_fingerprint="dev_test",
        hostname="camera-01",
        platform="linux",
        arch="aarch64",
        requested_profile="edge",
    )
    return EnrollmentService(store).claim(
        JoinTicket(envelope=envelope, secret=secret),
        claim,
        observed_at="2026-08-22T09:00:01Z",
    )


def _observe_profile(name: str) -> CapabilityGovernanceProfile:
    return CapabilityGovernanceProfile.build(
        name,
        CapabilityLevel.OBSERVE,
        risks=RiskDimensions(authority=0, autonomy=0),
    )


def test_pipeline_stops_at_registered_when_capability_is_ungoverned(tmp_path) -> None:
    receipt = _receipt(tmp_path)
    manifest = NodeCapabilityManifest(
        identity=receipt.node_identity,
        observed_at="2026-08-22T09:00:02Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )
    coordinator = NodeOnboardingCoordinator(nodes=NodeRegistry(), governance=GovernanceRegistry())
    pipeline = NodeOnboardingPipeline(
        directory=NodeDirectoryStore(str(tmp_path / "nodes.db")),
        coordinator=coordinator,
    )

    result = pipeline.ingest(receipt=receipt, manifest=manifest, governance_ref="should-not-bypass")
    assert result.checkpoint.lifecycle is NodeLifecycle.REGISTERED
    assert result.governance.can_activate is False
    assert result.governance.governance_gaps[0].capability == "camera.observe"


def test_pipeline_can_activate_only_after_governance_profile_exists(tmp_path) -> None:
    receipt = _receipt(tmp_path)
    manifest = NodeCapabilityManifest(
        identity=receipt.node_identity,
        observed_at="2026-08-22T09:00:02Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )
    governance = GovernanceRegistry((_observe_profile("camera.observe"),))
    coordinator = NodeOnboardingCoordinator(nodes=NodeRegistry(), governance=governance)
    directory = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    pipeline = NodeOnboardingPipeline(directory=directory, coordinator=coordinator)

    result = pipeline.ingest(receipt=receipt, manifest=manifest, governance_ref="gov-profile-set-v1")
    assert result.governance.can_activate is True
    assert result.checkpoint.lifecycle is NodeLifecycle.ACTIVE
    assert result.checkpoint.governance_ref == "gov-profile-set-v1"
    assert directory.checkpoint(receipt.node_identity.node_id).lifecycle is NodeLifecycle.ACTIVE


def test_reconnect_new_capability_produces_delta_and_returns_to_governance(tmp_path) -> None:
    receipt = _receipt(tmp_path)
    governance = GovernanceRegistry((_observe_profile("camera.observe"),))
    coordinator = NodeOnboardingCoordinator(nodes=NodeRegistry(), governance=governance)
    directory = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    pipeline = NodeOnboardingPipeline(directory=directory, coordinator=coordinator)

    first = NodeCapabilityManifest(
        identity=receipt.node_identity,
        observed_at="2026-08-22T09:00:02Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )
    assert pipeline.ingest(receipt=receipt, manifest=first, governance_ref="gov-v1").checkpoint.lifecycle is NodeLifecycle.ACTIVE

    second = NodeCapabilityManifest(
        identity=receipt.node_identity,
        observed_at="2026-08-22T09:10:00Z",
        capabilities=(
            CapabilityObservation("camera.observe", "test"),
            CapabilityObservation("microphone.observe", "test"),
        ),
    )
    result = pipeline.ingest(receipt=receipt, manifest=second, governance_ref="gov-v1")
    assert result.capability_delta is not None
    assert {change.capability for change in result.capability_delta.changes} == {"microphone.observe"}
    assert result.checkpoint.lifecycle is NodeLifecycle.REGISTERED
    assert result.governance.can_activate is False


def test_revoked_node_cannot_self_rejoin(tmp_path) -> None:
    receipt = _receipt(tmp_path)
    governance = GovernanceRegistry((_observe_profile("camera.observe"),))
    coordinator = NodeOnboardingCoordinator(nodes=NodeRegistry(), governance=governance)
    directory = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    pipeline = NodeOnboardingPipeline(directory=directory, coordinator=coordinator)
    manifest = NodeCapabilityManifest(
        identity=receipt.node_identity,
        observed_at="2026-08-22T09:00:02Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )
    pipeline.ingest(receipt=receipt, manifest=manifest, governance_ref="gov-v1")
    NodeRevocationService(directory).revoke(
        receipt.node_identity.node_id,
        actor_ref="owner",
        governance_ref="gov-revoke",
        reason="retired",
        observed_at="2026-08-22T09:05:00Z",
    )

    with pytest.raises(PermissionError, match="revoked Node"):
        pipeline.ingest(receipt=receipt, manifest=manifest, governance_ref="gov-v1")

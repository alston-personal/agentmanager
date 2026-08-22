import pytest

from agent_core.node_directory_store import NodeDirectoryStore
from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest, NodeIdentity
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


def _manifest() -> NodeCapabilityManifest:
    return NodeCapabilityManifest(
        identity=NodeIdentity("node-a", "realm-personal", "node-a", "linux", "aarch64"),
        observed_at="2026-08-22T09:00:00Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )


def test_directory_persists_manifest_and_checkpoint_across_instances(tmp_path) -> None:
    path = str(tmp_path / "nodes.db")
    manifest = _manifest()
    store = NodeDirectoryStore(path)
    store.save_manifest(manifest)
    identified = OnboardingCheckpoint(
        node_id="node-a",
        lifecycle=NodeLifecycle.IDENTIFIED,
        observed_at=manifest.observed_at,
        identity_id=manifest.identity.identity_id,
    )
    store.initialize_node(identified)
    discovered = OnboardingCheckpoint(
        node_id="node-a",
        lifecycle=NodeLifecycle.DISCOVERED,
        observed_at=manifest.observed_at,
        identity_id=manifest.identity.identity_id,
        capability_manifest_id=manifest.manifest_id,
    )
    store.advance(discovered)

    reopened = NodeDirectoryStore(path)
    assert reopened.checkpoint("node-a") == discovered
    assert reopened.latest_manifest("node-a") == manifest
    assert reopened.nodes_with_capability("camera.observe") == ("node-a",)


def test_directory_rejects_skipping_governance_and_active_without_governance_ref(tmp_path) -> None:
    store = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    manifest = _manifest()
    store.save_manifest(manifest)
    registered = OnboardingCheckpoint(
        node_id="node-a",
        lifecycle=NodeLifecycle.REGISTERED,
        observed_at=manifest.observed_at,
        identity_id=manifest.identity.identity_id,
        capability_manifest_id=manifest.manifest_id,
    )
    store.initialize_node(registered)

    active = OnboardingCheckpoint(
        node_id="node-a",
        lifecycle=NodeLifecycle.ACTIVE,
        observed_at=manifest.observed_at,
        identity_id=manifest.identity.identity_id,
        capability_manifest_id=manifest.manifest_id,
    )
    with pytest.raises(ValueError, match="invalid Node lifecycle transition"):
        store.advance(active)

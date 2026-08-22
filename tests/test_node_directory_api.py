from agent_core.node_directory_api import NodeDirectoryApi
from agent_core.node_directory_store import NodeDirectoryStore
from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest, NodeIdentity
from runtime_core.onboarding_v1 import NodeLifecycle, OnboardingCheckpoint


def test_directory_api_lists_nodes_and_capabilities(tmp_path) -> None:
    store = NodeDirectoryStore(str(tmp_path / "nodes.db"))
    identity = NodeIdentity("node-a", "realm-personal", "node-a", "linux", "aarch64")
    manifest = NodeCapabilityManifest(
        identity=identity,
        observed_at="2026-08-22T09:00:00Z",
        capabilities=(CapabilityObservation("camera.observe", "test"),),
    )
    store.save_manifest(manifest)
    store.initialize_node(
        OnboardingCheckpoint(
            node_id="node-a",
            lifecycle=NodeLifecycle.REGISTERED,
            observed_at=manifest.observed_at,
            identity_id=identity.identity_id,
            capability_manifest_id=manifest.manifest_id,
        )
    )

    api = NodeDirectoryApi(store)
    listed = api.list_nodes()
    assert listed["nodes"][0]["node_id"] == "node-a"
    assert listed["nodes"][0]["capability_count"] == 1

    caps = api.capabilities("node-a")
    assert caps["capabilities"][0]["capability"] == "camera.observe"
    assert caps["capabilities"][0]["state"] == "discovered"

    reverse = api.nodes_for_capability("camera.observe")
    assert reverse["nodes"] == ["node-a"]

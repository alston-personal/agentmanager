from agent_core.node_registry import NodeRegistry
from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest, NodeIdentity


def _manifest(node_id: str, capability: str) -> NodeCapabilityManifest:
    return NodeCapabilityManifest(
        identity=NodeIdentity(node_id, "realm-personal", node_id, "linux", "aarch64"),
        observed_at="2026-08-22T09:00:00Z",
        capabilities=(CapabilityObservation(capability, "test"),),
    )


def test_registry_queries_nodes_by_capability_without_authorizing_them() -> None:
    registry = NodeRegistry()
    registry.register_many((_manifest("node-a", "camera.observe"), _manifest("node-b", "repo.read")))

    assert registry.node_ids() == ("node-a", "node-b")
    matches = registry.nodes_with_capability("camera.observe")
    assert len(matches) == 1
    assert matches[0].node_id == "node-a"
    assert matches[0].capability.state.value == "discovered"

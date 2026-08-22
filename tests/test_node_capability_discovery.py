from agentos_node.capability_discovery import DiscoveryContext, discover_linux_capabilities


def test_discovery_reports_presence_without_authority() -> None:
    available = {"git", "docker", "curl", "ffmpeg"}

    def command_exists(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in available else None

    manifest = discover_linux_capabilities(
        DiscoveryContext(
            realm_id="realm-personal",
            node_id="node-oracle-01",
            observed_at="2026-08-22T09:00:00Z",
        ),
        command_exists=command_exists,
        hostname="oracle",
    )

    names = {item.capability for item in manifest.capabilities}
    assert {"node.status", "node.capabilities.read", "repo.read", "container.runtime.observe", "http.client.observe", "media.transform"} <= names
    assert manifest.metadata["authorization_inferred"] is False
    assert all(item.state.value in {"discovered", "registered", "unavailable"} for item in manifest.capabilities)

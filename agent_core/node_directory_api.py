"""Transport-neutral read API for the AgentOS Node directory."""

from __future__ import annotations

from dataclasses import asdict

from agent_core.node_directory_store import NodeDirectoryStore


class NodeDirectoryApi:
    def __init__(self, directory: NodeDirectoryStore) -> None:
        self.directory = directory

    def list_nodes(self) -> dict[str, object]:
        nodes: list[dict[str, object]] = []
        for node_id in self.directory.node_ids():
            checkpoint = self.directory.checkpoint(node_id)
            manifest = self.directory.latest_manifest(node_id)
            nodes.append(
                {
                    "node_id": node_id,
                    "lifecycle": checkpoint.lifecycle.value if checkpoint else "unknown",
                    "manifest_id": manifest.manifest_id if manifest else None,
                    "capability_count": len(manifest.capabilities) if manifest else 0,
                }
            )
        return {"schema": "agentos.node-directory-list/v1", "nodes": nodes}

    def node(self, node_id: str) -> dict[str, object]:
        checkpoint = self.directory.checkpoint(node_id)
        if checkpoint is None:
            raise KeyError(f"unknown Node: {node_id}")
        manifest = self.directory.latest_manifest(node_id)
        return {
            "schema": "agentos.node-directory-entry/v1",
            "node_id": node_id,
            "checkpoint": {**asdict(checkpoint), "lifecycle": checkpoint.lifecycle.value},
            "manifest": asdict(manifest) if manifest else None,
            "manifest_id": manifest.manifest_id if manifest else None,
        }

    def capabilities(self, node_id: str) -> dict[str, object]:
        manifest = self.directory.latest_manifest(node_id)
        if manifest is None:
            raise KeyError(f"Node has no capability manifest: {node_id}")
        return {
            "schema": "agentos.node-capabilities/v1",
            "node_id": node_id,
            "manifest_id": manifest.manifest_id,
            "capabilities": [
                {
                    "capability": item.capability,
                    "state": item.state.value,
                    "source": item.source,
                    "device_ref": item.device_ref,
                    "adapter": item.adapter,
                    "attributes": item.attributes,
                    "risk_tags": list(item.risk_tags),
                }
                for item in manifest.capabilities
            ],
        }

    def nodes_for_capability(self, capability: str) -> dict[str, object]:
        return {
            "schema": "agentos.capability-nodes/v1",
            "capability": capability,
            "nodes": list(self.directory.nodes_with_capability(capability)),
        }

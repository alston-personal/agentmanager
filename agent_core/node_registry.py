"""Queryable registry for AgentOS Node identity and capability manifests.

The registry records what Nodes have reported.  It does not convert discovery
into authority; callers must still resolve authorization through governance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest


@dataclass(frozen=True)
class NodeCapabilityView:
    node_id: str
    manifest_id: str
    capability: CapabilityObservation


class NodeRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, NodeCapabilityManifest] = {}

    def register_manifest(self, manifest: NodeCapabilityManifest) -> str:
        self._manifests[manifest.identity.node_id] = manifest
        return manifest.manifest_id

    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._manifests))

    def manifest(self, node_id: str) -> NodeCapabilityManifest | None:
        return self._manifests.get(node_id)

    def capabilities(self, node_id: str) -> tuple[CapabilityObservation, ...]:
        manifest = self.manifest(node_id)
        return manifest.capabilities if manifest else ()

    def nodes_with_capability(self, capability: str) -> tuple[NodeCapabilityView, ...]:
        matches: list[NodeCapabilityView] = []
        for node_id in self.node_ids():
            manifest = self._manifests[node_id]
            observation = manifest.capability(capability)
            if observation is not None:
                matches.append(NodeCapabilityView(node_id, manifest.manifest_id, observation))
        return tuple(matches)

    def register_many(self, manifests: Iterable[NodeCapabilityManifest]) -> tuple[str, ...]:
        return tuple(self.register_manifest(manifest) for manifest in manifests)

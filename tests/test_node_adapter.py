from __future__ import annotations

import sys
import types

import pytest

from agentos_node.node_adapter import AdapterRegistry, load_configured_adapters
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


class FakeCameraAdapter:
    adapter_id = "fake-camera"

    def capabilities(self):
        return ["camera.capture", "camera.status"]

    def describe(self):
        return {"kind": "test", "device_count": 1}

    def execute(self, task):
        action = task.get("action")
        if action == "camera.status":
            return {"camera_ready": True}
        if action == "camera.capture":
            return {"asset_ref": "asset://fake/frame-001"}
        raise ValueError("unsupported fake camera action")


class DuplicateCameraAdapter(FakeCameraAdapter):
    adapter_id = "duplicate-camera"

    def capabilities(self):
        return ["camera.capture"]


def test_adapter_capabilities_join_node_manifest_and_execute():
    registry = AdapterRegistry([FakeCameraAdapter()])
    client = ThinClient(
        NodeIdentity("realm-test", "glasses-01"),
        ThinClientPolicy(),
        adapters=registry,
    )

    manifest = client.capability_manifest()
    assert "camera.capture" in manifest["capabilities"]
    assert "camera.status" in manifest["capabilities"]
    assert manifest["adapters"] == [{
        "adapter_id": "fake-camera",
        "capabilities": ["camera.capture", "camera.status"],
        "metadata": {"kind": "test", "device_count": 1},
    }]

    receipt = client.execute({
        "schema": "agentos.node-task/v0.1",
        "task_id": "capture-1",
        "action": "camera.capture",
    })
    assert receipt["ok"] is True
    assert receipt["asset_ref"] == "asset://fake/frame-001"
    assert receipt["adapter_id"] == "fake-camera"


def test_adapter_cannot_shadow_another_adapter_capability():
    with pytest.raises(ValueError, match="duplicate adapter capability"):
        AdapterRegistry([FakeCameraAdapter(), DuplicateCameraAdapter()])


def test_adapter_loading_is_explicit_and_module_based(monkeypatch):
    module = types.ModuleType("agentos_test_camera_adapter")
    module.create_adapter = lambda: FakeCameraAdapter()
    monkeypatch.setitem(sys.modules, module.__name__, module)

    adapters = load_configured_adapters(module.__name__)
    registry = AdapterRegistry(adapters)
    assert registry.capabilities() == ["camera.capture", "camera.status"]


def test_unknown_action_still_fails_closed():
    client = ThinClient(
        NodeIdentity("realm-test", "node-test"),
        ThinClientPolicy(),
        adapters=AdapterRegistry(),
    )
    receipt = client.execute({
        "schema": "agentos.node-task/v0.1",
        "task_id": "unknown-1",
        "action": "device.do-anything",
    })
    assert receipt["ok"] is False
    assert "unsupported action" in receipt["error"]


def test_node_registry_persists_adapter_topology(tmp_path):
    from agent_core.node_registry import NodeRegistry

    client = ThinClient(
        NodeIdentity("realm-test", "glasses-02"),
        ThinClientPolicy(),
        adapters=AdapterRegistry([FakeCameraAdapter()]),
    )
    registry = NodeRegistry(path=tmp_path / "nodes.json")
    registry.register_manifest(client.capability_manifest())

    node = registry.node_map()["nodes"][0]
    assert node["node_id"] == "glasses-02"
    assert node["adapters"][0]["adapter_id"] == "fake-camera"
    assert "camera.capture" in node["adapters"][0]["capabilities"]

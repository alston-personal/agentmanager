from dataclasses import replace

import pytest

from runtime_core.node_v1 import (
    CapabilityObservation,
    CapabilityState,
    NodeCapabilityManifest,
    NodeIdentity,
    diff_manifests,
)


def _identity() -> NodeIdentity:
    return NodeIdentity(
        node_id="node-oracle-01",
        realm_id="realm-personal",
        hostname="oracle",
        platform="linux",
        arch="aarch64",
    )


def test_discovery_cannot_self_authorize() -> None:
    with pytest.raises(ValueError, match="self-authorize"):
        CapabilityObservation(
            capability="camera.observe",
            source="device:/dev/video0",
            state=CapabilityState.AUTHORIZED,
        )


def test_manifest_is_content_addressed_and_order_stable_by_value() -> None:
    manifest = NodeCapabilityManifest(
        identity=_identity(),
        observed_at="2026-08-22T09:00:00Z",
        capabilities=(CapabilityObservation("repo.read", "command:git"),),
    )
    assert manifest.manifest_id.startswith("ncap_")
    assert manifest.manifest_id == replace(manifest).manifest_id


def test_capability_delta_reports_add_remove_and_state_change() -> None:
    previous = NodeCapabilityManifest(
        identity=_identity(),
        observed_at="t0",
        capabilities=(
            CapabilityObservation("repo.read", "command:git"),
            CapabilityObservation("usb.observe", "device:/dev/bus/usb"),
        ),
    )
    current = NodeCapabilityManifest(
        identity=_identity(),
        observed_at="t1",
        capabilities=(
            CapabilityObservation("repo.read", "command:git", state=CapabilityState.REGISTERED),
            CapabilityObservation("camera.observe", "device:/dev/video0"),
        ),
    )
    delta = diff_manifests(previous, current)
    names = {change.capability for change in delta.changes}
    assert names == {"repo.read", "usb.observe", "camera.observe"}

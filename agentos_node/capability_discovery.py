"""Read-only host capability discovery for AgentOS Nodes.

Discovery reports presence only. It never authorizes device access, opens a
camera/microphone, mounts storage, sends USB traffic, or changes host state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import shutil
import socket
from typing import Callable, Iterable

from runtime_core.node_v1 import CapabilityObservation, NodeCapabilityManifest, NodeIdentity


@dataclass(frozen=True)
class DiscoveryContext:
    realm_id: str
    node_id: str
    observed_at: str
    profile: str = "edge"


def _exists_any(paths: Iterable[Path]) -> bool:
    return any(path.exists() for path in paths)


def _device_paths(pattern: str) -> list[str]:
    return sorted(str(path) for path in Path("/dev").glob(pattern))


def _base_observations(command_exists: Callable[[str], str | None]) -> list[CapabilityObservation]:
    found = [
        CapabilityObservation("node.status", "builtin"),
        CapabilityObservation("node.capabilities.read", "builtin"),
    ]
    if command_exists("git"):
        found.append(CapabilityObservation("repo.read", "command:git"))
    if command_exists("docker"):
        found.append(CapabilityObservation("container.runtime.observe", "command:docker"))
    if command_exists("curl"):
        found.append(CapabilityObservation("http.client.observe", "command:curl"))
    if command_exists("ffmpeg"):
        found.append(CapabilityObservation("media.transform", "command:ffmpeg"))
    return found


def _linux_device_observations(command_exists: Callable[[str], str | None]) -> list[CapabilityObservation]:
    found: list[CapabilityObservation] = []
    video = _device_paths("video*")
    if video:
        found.append(
            CapabilityObservation(
                "camera.observe",
                "device:/dev/video*",
                device_ref="video-device",
                attributes={"device_count": len(video)},
                risk_tags=("privacy", "sensor"),
            )
        )
    if _exists_any([Path("/dev/snd")]):
        found.append(
            CapabilityObservation(
                "microphone.observe",
                "device:/dev/snd",
                device_ref="sound-device",
                risk_tags=("privacy", "sensor"),
            )
        )
    if command_exists("lpstat") or command_exists("lp"):
        found.append(CapabilityObservation("printer.observe", "command:cups", risk_tags=("external-effect",)))
    usb = _device_paths("bus/usb/*/*")
    if usb:
        found.append(
            CapabilityObservation(
                "usb.observe",
                "device:/dev/bus/usb",
                device_ref="usb-bus",
                attributes={"device_count": len(usb)},
                risk_tags=("device-io",),
            )
        )
    if command_exists("bluetoothctl"):
        found.append(CapabilityObservation("bluetooth.observe", "command:bluetoothctl", risk_tags=("radio", "device-io")))
    return found


def discover_capabilities_for_identity(
    identity: NodeIdentity,
    *,
    observed_at: str,
    command_exists: Callable[[str], str | None] = shutil.which,
) -> NodeCapabilityManifest:
    """Discover capabilities while preserving the already-claimed Node identity.

    Platform-specific deep device probes are intentionally conservative. Linux
    has a metadata-only adapter today; other platforms receive portable software
    observations until dedicated read-only adapters are implemented.
    """

    found = _base_observations(command_exists)
    if identity.platform.lower() == "linux":
        found.extend(_linux_device_observations(command_exists))
    capabilities = tuple(sorted(found, key=lambda item: item.capability))
    return NodeCapabilityManifest(
        identity=identity,
        observed_at=observed_at,
        capabilities=capabilities,
        metadata={
            "discovery_mode": "read-only",
            "authorization_inferred": False,
            "platform_adapter": "linux" if identity.platform.lower() == "linux" else "portable-base",
        },
    )


def discover_linux_capabilities(
    context: DiscoveryContext,
    *,
    command_exists: Callable[[str], str | None] = shutil.which,
    hostname: str | None = None,
) -> NodeCapabilityManifest:
    """Compatibility wrapper for conservative, metadata-only Linux discovery."""

    identity = NodeIdentity(
        node_id=context.node_id,
        realm_id=context.realm_id,
        hostname=hostname or socket.gethostname(),
        platform=platform.system().lower(),
        arch=platform.machine().lower(),
        profile=context.profile,
        labels=("linux",),
    )
    return discover_capabilities_for_identity(identity, observed_at=context.observed_at, command_exists=command_exists)

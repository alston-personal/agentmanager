"""Read-only host capability discovery for AgentOS Nodes.

Discovery reports presence only.  It never authorizes device access, opens a
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


def discover_linux_capabilities(
    context: DiscoveryContext,
    *,
    command_exists: Callable[[str], str | None] = shutil.which,
    hostname: str | None = None,
) -> NodeCapabilityManifest:
    """Create a conservative, metadata-only Linux capability manifest."""

    identity = NodeIdentity(
        node_id=context.node_id,
        realm_id=context.realm_id,
        hostname=hostname or socket.gethostname(),
        platform=platform.system().lower(),
        arch=platform.machine().lower(),
        profile=context.profile,
        labels=("linux",),
    )

    found: list[CapabilityObservation] = []

    def add(name: str, source: str, **kwargs: object) -> None:
        found.append(CapabilityObservation(capability=name, source=source, **kwargs))

    add("node.status", "builtin")
    add("node.capabilities.read", "builtin")

    if command_exists("git"):
        add("repo.read", "command:git")
    if command_exists("docker"):
        add("container.runtime.observe", "command:docker")
    if command_exists("curl"):
        add("http.client.observe", "command:curl")

    video = _device_paths("video*")
    if video:
        add(
            "camera.observe",
            "device:/dev/video*",
            device_ref="video-device",
            attributes={"device_count": len(video)},
            risk_tags=("privacy", "sensor"),
        )

    sound_paths = [Path("/dev/snd")]
    if _exists_any(sound_paths):
        add(
            "microphone.observe",
            "device:/dev/snd",
            device_ref="sound-device",
            risk_tags=("privacy", "sensor"),
        )

    if command_exists("lpstat") or command_exists("lp"):
        add("printer.observe", "command:cups", risk_tags=("external-effect",))

    usb = _device_paths("bus/usb/*/*")
    if usb:
        add(
            "usb.observe",
            "device:/dev/bus/usb",
            device_ref="usb-bus",
            attributes={"device_count": len(usb)},
            risk_tags=("device-io",),
        )

    if command_exists("bluetoothctl"):
        add("bluetooth.observe", "command:bluetoothctl", risk_tags=("radio", "device-io"))

    if command_exists("ffmpeg"):
        add("media.transform", "command:ffmpeg")

    capabilities = tuple(sorted(found, key=lambda item: item.capability))
    return NodeCapabilityManifest(
        identity=identity,
        observed_at=context.observed_at,
        capabilities=capabilities,
        metadata={"discovery_mode": "read-only", "authorization_inferred": False},
    )

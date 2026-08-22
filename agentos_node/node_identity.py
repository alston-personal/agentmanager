"""Local identity material for AgentOS Node onboarding.

Private key material never leaves the Node. The reference implementation uses
OpenSSH Ed25519 keys because ssh-keygen is widely available on Linux/macOS and
modern Windows. Embedded/native clients may provide an equivalent key backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import platform
import shutil
import socket
import subprocess


@dataclass(frozen=True)
class LocalNodeIdentityMaterial:
    public_key: str
    device_fingerprint: str
    hostname: str
    platform: str
    arch: str


class NodeKeyProvisionError(RuntimeError):
    pass


def _default_identity_dir() -> Path:
    return Path.home() / ".agentos" / "node"


def _stable_machine_material() -> bytes:
    candidates = [Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")]
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value.encode("utf-8")
    fallback = f"{socket.gethostname()}\0{platform.system()}\0{platform.machine()}".encode("utf-8")
    return fallback


def device_fingerprint() -> str:
    return "dev_" + sha256(_stable_machine_material()).hexdigest()[:32]


def ensure_node_identity(identity_dir: Path | None = None) -> LocalNodeIdentityMaterial:
    directory = identity_dir or _default_identity_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

    private_key = directory / "identity_ed25519"
    public_key = directory / "identity_ed25519.pub"
    if not private_key.exists() or not public_key.exists():
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            raise NodeKeyProvisionError("ssh-keygen is required by the Python reference identity backend")
        result = subprocess.run(
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-C", "agentos-node", "-f", str(private_key)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise NodeKeyProvisionError("failed to provision Node identity key")

    try:
        os.chmod(private_key, 0o600)
        os.chmod(public_key, 0o644)
    except OSError:
        pass

    value = public_key.read_text(encoding="utf-8").strip()
    if not value.startswith("ssh-ed25519 "):
        raise NodeKeyProvisionError("unexpected Node public key format")

    return LocalNodeIdentityMaterial(
        public_key=value,
        device_fingerprint=device_fingerprint(),
        hostname=socket.gethostname(),
        platform=platform.system().lower(),
        arch=platform.machine().lower(),
    )

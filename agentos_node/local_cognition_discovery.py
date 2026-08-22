"""Safe local cognition discovery for Node onboarding reconciliation.

Only explicitly supplied roots are scanned. Sensitive-looking paths, symlinks,
large files and unsupported formats are ignored. The scanner emits hashes and
provenance descriptors, never raw content.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Iterable

from agent_core.node_reconciliation import LocalCognitionDescriptor


_ALLOWED_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
_SENSITIVE_PARTS = {
    "secret",
    "secrets",
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "token",
    "tokens",
    "browser-profile",
    "browser_profile",
    "private-key",
    "private_key",
}


def _looks_sensitive(path: Path) -> bool:
    return any(part.lower() in _SENSITIVE_PARTS for part in path.parts)


def _kind(path: Path) -> str:
    name = path.name.lower()
    if "memory" in name:
        return "memory"
    if "knowledge" in name:
        return "knowledge"
    if "experience" in name:
        return "experience"
    if "state" in name:
        return "state_descriptor"
    return "local_cognition"


def discover_local_cognition(
    roots: Iterable[Path],
    *,
    project_id: str | None = None,
    max_file_bytes: int = 16 * 1024 * 1024,
) -> tuple[LocalCognitionDescriptor, ...]:
    descriptors: list[LocalCognitionDescriptor] = []
    for supplied_root in roots:
        root = supplied_root.expanduser().resolve()
        if not root.exists() or not root.is_dir() or _looks_sensitive(root):
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if _looks_sensitive(relative) or path.suffix.lower() not in _ALLOWED_SUFFIXES:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size < 0 or size > max_file_bytes:
                continue
            try:
                digest = sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            descriptors.append(
                LocalCognitionDescriptor(
                    local_ref=str(relative),
                    content_hash="sha256:" + digest,
                    kind=_kind(path),
                    provenance=f"node-local:{root.name}",
                    project_id=project_id,
                )
            )
    return tuple(sorted(descriptors, key=lambda item: (item.content_hash, item.local_ref)))

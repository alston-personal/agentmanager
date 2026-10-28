"""Receive a separately signed Paw request into the worker-owned private inbox.

This is a transport boundary, NEVER an issuer. The signer key is not accessible
here. A valid signature and a fresh exact lease are mandatory.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_lifecycle import EmployeeLifecycle
from agentos_node.paw_engineering_request import trusted_request_filename
from agentos_node.paw_engineering_public_signature import verify_paw_public_signature
from agentos_node.paw_engineering_grant import (
    validate_paw_engineering_grant, require_canonical_paw_authority,
    require_live_paw_lease,
)
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def receive_authorized_paw_request(*, signed_source: Path, authority_dir: Path,
                                   runtime_root: Path, assignment_id: str,
                                   lease_id: str, wake_id: str,
                                   presence_generation: int,
                                   registry_path: Path) -> Path:
    """Transport an independently signed, exact-lease grant; never sign it."""
    directory = Path(authority_dir)
    source = Path(signed_source)
    if (directory.is_symlink() or not directory.is_dir()
            or directory.stat().st_uid != os.geteuid()
            or directory.stat().st_mode & 0o077):
        raise PawWorktreeBoundaryError("paw_delivery_directory_not_trusted")
    key_file = directory / "paw-470-issuer.pub"
    if key_file.is_symlink() or not key_file.is_file():
        raise PawWorktreeBoundaryError("paw_delivery_public_key_missing")
    key_stat = key_file.stat()
    if (not stat.S_ISREG(key_stat.st_mode) or key_stat.st_uid != os.geteuid()
            or key_stat.st_mode & 0o077 or key_stat.st_nlink != 1):
        raise PawWorktreeBoundaryError("paw_delivery_public_key_untrusted")
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 65536:
        raise PawWorktreeBoundaryError("paw_delivery_source_invalid")
    request = verify_paw_public_signature(
        json.loads(source.read_text(encoding="utf-8")), public_key=key_file.read_bytes()
    )
    runtime = EmployeeRuntime(runtime_root)
    lifecycle = EmployeeLifecycle(runtime)
    lease = lifecycle.get_lease(assignment_id)
    if lease is None:
        raise PawWorktreeBoundaryError("paw_delivery_lease_missing")
    grant = validate_paw_engineering_grant(
        request["grant"], expected_assignment_id=assignment_id,
        expected_wake_id=wake_id,
        expected_presence_generation=presence_generation,
        expected_lease_generation=lease.generation,
        allow_dynamic_assignment=True,
    )
    require_canonical_paw_authority(grant, registry_path=registry_path, runtime=runtime)
    require_live_paw_lease(grant, lifecycle=lifecycle, expected_lease_id=lease_id)
    dest = directory / trusted_request_filename(assignment_id)
    payload = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    temp = None
    try:
        fd, name = tempfile.mkstemp(prefix=".paw-delivery-", dir=directory)
        temp = Path(name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        require_live_paw_lease(grant, lifecycle=lifecycle, expected_lease_id=lease_id)
        try:
            os.link(temp, dest, follow_symlinks=False)
        except FileExistsError as exc:
            raise PawWorktreeBoundaryError("paw_delivery_already_exists") from exc
        dirfd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return dest

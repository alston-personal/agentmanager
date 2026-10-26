"""Authenticated, replay-resistant Paw engineering request envelope.

The owner-controlled issuer must sign requests with a secret not available to
the Wake capsule producer. Merely placing a JSON file never authorizes work.
"""
from __future__ import annotations
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Mapping
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError

SCHEMA = "agentos.paw-engineering-request/v1"
KEYS = {"schema", "grant", "expected_sha256", "replacement", "signature"}
MAX_BYTES = 65536


def canonical_payload(request: Mapping[str, Any]) -> bytes:
    return json.dumps(
        {k: request[k] for k in sorted(KEYS - {"signature"})},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def authenticate_paw_request(
    request: Mapping[str, Any], *, issuer_key: bytes,
) -> dict[str, Any]:
    if not isinstance(request, dict) or set(request) != KEYS:
        raise PawWorktreeBoundaryError("paw_signed_request_shape_invalid")
    if request["schema"] != SCHEMA or not isinstance(issuer_key, bytes) or len(issuer_key) < 32:
        raise PawWorktreeBoundaryError("paw_signed_request_issuer_unavailable")
    if not isinstance(request["grant"], dict) or not isinstance(request["replacement"], str):
        raise PawWorktreeBoundaryError("paw_signed_request_payload_invalid")
    digest = request["expected_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise PawWorktreeBoundaryError("paw_signed_request_digest_invalid")
    content = canonical_payload(request)
    if len(content) > MAX_BYTES:
        raise PawWorktreeBoundaryError("paw_signed_request_too_large")
    sig = request["signature"]
    expected = hmac.new(issuer_key, content, hashlib.sha256).hexdigest()
    if not isinstance(sig, str) or not hmac.compare_digest(sig, expected):
        raise PawWorktreeBoundaryError("paw_signed_request_authentication_failed")
    return dict(request)


def read_authenticated_paw_request(path: Path, *, issuer_key: bytes) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise PawWorktreeBoundaryError("paw_signed_request_file_invalid")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise PawWorktreeBoundaryError("paw_signed_request_file_invalid") from exc
    return authenticate_paw_request(data, issuer_key=issuer_key)


def trusted_request_filename(assignment_id: str) -> str:
    """Separate signed request envelopes for independently authorized assignments.

    The original A keeps its legacy name. New WorkItems use an opaque filename,
    never a user-supplied path. This lookup does NOT issue execution authority.
    """
    from agentos_node.paw_engineering_worktree import _ID
    if not isinstance(assignment_id, str) or not _ID.fullmatch(assignment_id):
        raise PawWorktreeBoundaryError("paw_issuer_assignment_invalid")
    if assignment_id == "paw-470-inspection-v1":
        return "paw-470-request.json"
    return "paw-request-" + hashlib.sha256(assignment_id.encode("utf-8")).hexdigest() + ".json"

def publish_trusted_paw_request(
    authority_dir: Path, *, assignment_id: str, signed_request: Mapping[str, Any],
    issuer_key: bytes,
) -> Path:
    """Issuer-side, immutable delivery of an authenticated request.

    Call ONLY after issue_paw_request validated the live lease and policy.
    The worker reads this artifact; it must never invoke this publisher.
    """
    import os
    import stat
    directory = Path(authority_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise PawWorktreeBoundaryError("paw_issuer_directory_not_trusted")
    mode = directory.stat()
    if mode.st_uid != os.geteuid() or mode.st_mode & 0o077:
        raise PawWorktreeBoundaryError("paw_issuer_directory_not_trusted")
    verified = authenticate_paw_request(signed_request, issuer_key=issuer_key)
    if verified["grant"].get("assignment_id") != assignment_id:
        raise PawWorktreeBoundaryError("paw_issuer_assignment_invalid")
    path = directory / trusted_request_filename(assignment_id)
    payload = json.dumps(verified, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise PawWorktreeBoundaryError("paw_signed_request_too_large")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise PawWorktreeBoundaryError("paw_issuer_request_already_exists") from exc
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        dirfd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path

def issue_paw_request(
    *, grant: Mapping[str, Any], expected_sha256: str,
    replacement: str, issuer_key: bytes,
    trusted_assignment_id: str, trusted_wake_id: str,
    trusted_presence_generation: int, trusted_lease_generation: int,
    lifecycle: object, trusted_lease_id: str, registry_path: Path,
    trusted_runtime: object | None = None,
) -> dict[str, Any]:
    """Trusted control-plane entry; caller owns key and live lifecycle."""
    from agentos_node.paw_engineering_grant import (
        validate_paw_engineering_grant, require_canonical_paw_authority,
        require_live_paw_lease,
    )
    if trusted_assignment_id != "paw-470-inspection-v1" and trusted_runtime is None:
        raise PawWorktreeBoundaryError("paw_issuer_assignment_invalid")
    validated = validate_paw_engineering_grant(
        dict(grant), expected_assignment_id=trusted_assignment_id,
        expected_wake_id=trusted_wake_id,
        expected_presence_generation=trusted_presence_generation,
        expected_lease_generation=trusted_lease_generation,
        allow_dynamic_assignment=trusted_runtime is not None,
    )
    require_canonical_paw_authority(validated, registry_path=registry_path, runtime=trusted_runtime)
    require_live_paw_lease(validated, lifecycle=lifecycle, expected_lease_id=trusted_lease_id)
    request = {
        "schema": SCHEMA, "grant": dict(grant),
        "expected_sha256": expected_sha256, "replacement": replacement,
        "signature": "",
    }
    if not isinstance(issuer_key, bytes) or len(issuer_key) < 32:
        raise PawWorktreeBoundaryError("paw_signed_request_issuer_unavailable")
    request["signature"] = hmac.new(
        issuer_key, canonical_payload(request), hashlib.sha256,
    ).hexdigest()
    authenticate_paw_request(request, issuer_key=issuer_key)
    return request


def issue_and_publish_trusted_paw_request(
    *, authority_dir: Path, assignment_id: str,
    grant: Mapping[str, Any], expected_sha256: str, replacement: str,
    issuer_key: bytes, trusted_wake_id: str, trusted_presence_generation: int,
    trusted_lease_generation: int, trusted_lease_id: str,
    lifecycle: object, registry_path: Path, trusted_runtime: object,
) -> Path:
    """Control-plane only: authorize against live lease, then publish once.

    This is NOT a worker entrypoint and never derives trust from a wake capsule.
    A separate privileged caller must own the issuer key and exact lifecycle.
    """
    signed = issue_paw_request(
        grant=grant, expected_sha256=expected_sha256, replacement=replacement,
        issuer_key=issuer_key, trusted_assignment_id=assignment_id,
        trusted_wake_id=trusted_wake_id,
        trusted_presence_generation=trusted_presence_generation,
        trusted_lease_generation=trusted_lease_generation,
        trusted_lease_id=trusted_lease_id,
        lifecycle=lifecycle, registry_path=registry_path,
        trusted_runtime=trusted_runtime,
    )
    from agentos_node.paw_engineering_grant import (
        validate_paw_engineering_grant, require_live_paw_lease,
    )
    validated = validate_paw_engineering_grant(
        grant, expected_assignment_id=assignment_id,
        expected_wake_id=trusted_wake_id,
        expected_presence_generation=trusted_presence_generation,
        expected_lease_generation=trusted_lease_generation,
        allow_dynamic_assignment=True,
    )
    require_live_paw_lease(validated, lifecycle=lifecycle, expected_lease_id=trusted_lease_id)
    return publish_trusted_paw_request(
        authority_dir, assignment_id=assignment_id,
        signed_request=signed, issuer_key=issuer_key,
    )

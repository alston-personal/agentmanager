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

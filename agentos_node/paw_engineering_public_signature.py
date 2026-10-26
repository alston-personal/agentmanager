"""Ed25519 verifier boundary for governed Paw requests.

Only the trusted issuer owns private signing bytes. The worker receives public
verification bytes and cannot mint grants. This module does not grant work.
"""
from __future__ import annotations

import base64
from typing import Mapping, Any

from agentos_node.paw_engineering_request import canonical_payload
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def verify_paw_public_signature(request: Mapping[str, Any], *, public_key: bytes) -> dict[str, Any]:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(request, dict) or not isinstance(public_key, bytes) or len(public_key) != 32:
        raise PawWorktreeBoundaryError("paw_public_signature_invalid")
    if set(request) != {"schema", "grant", "expected_sha256", "replacement", "signature"}:
        raise PawWorktreeBoundaryError("paw_signed_request_shape_invalid")
    try:
        signature = base64.b64decode(request["signature"], validate=True)
        if len(signature) != 64:
            raise ValueError("invalid signature length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical_payload(request))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise PawWorktreeBoundaryError("paw_public_signature_invalid") from exc
    return dict(request)


def sign_paw_public_request(request: Mapping[str, Any], *, private_key: bytes) -> dict[str, Any]:
    """Issuer-side ONLY; never call from employee worker or wake capsule."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if not isinstance(private_key, bytes) or len(private_key) != 32:
        raise PawWorktreeBoundaryError("paw_private_signing_key_invalid")
    if not isinstance(request, dict) or set(request) != {"schema", "grant", "expected_sha256", "replacement", "signature"}:
        raise PawWorktreeBoundaryError("paw_signed_request_shape_invalid")
    try:
        signer = Ed25519PrivateKey.from_private_bytes(private_key)
        signed = dict(request)
        signed["signature"] = base64.b64encode(signer.sign(canonical_payload(signed))).decode("ascii")
        return signed
    except (ValueError, TypeError) as exc:
        raise PawWorktreeBoundaryError("paw_private_signing_key_invalid") from exc

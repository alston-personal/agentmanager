import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from agentos_node.paw_engineering_public_signature import (
    sign_paw_public_request, verify_paw_public_signature,
)
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def test_public_key_verifies_but_cannot_mint_or_modify_request():
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    body = {
        "schema": "agentos.paw-engineering-request/v1",
        "grant": {"assignment_id": "paw-b", "lease_generation": 1},
        "expected_sha256": "a" * 64,
        "replacement": "safe",
        "signature": "",
    }
    signed = sign_paw_public_request(body, private_key=private_bytes)
    assert verify_paw_public_signature(signed, public_key=public_bytes) == signed
    with pytest.raises(PawWorktreeBoundaryError):
        verify_paw_public_signature({**signed, "replacement": "unsafe"}, public_key=public_bytes)
    with pytest.raises(PawWorktreeBoundaryError):
        verify_paw_public_signature(signed, public_key=b"bad")
    with pytest.raises(PawWorktreeBoundaryError):
        sign_paw_public_request(body, private_key=public_bytes[:16])

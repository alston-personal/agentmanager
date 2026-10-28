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


def test_trusted_public_issuer_publishes_and_cannot_overwrite(tmp_path, monkeypatch):
    import hashlib
    from agentos_node.paw_engineering_request import (
        issue_and_publish_trusted_paw_public_request,
        trusted_request_filename,
    )
    import agentos_node.paw_engineering_grant as policies
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    class Grant:
        work_id = "paw-work-b"
    leases_checked = []
    monkeypatch.setattr(policies, "validate_paw_engineering_grant", lambda *args, **kwargs: Grant())
    monkeypatch.setattr(policies, "require_canonical_paw_authority", lambda *args, **kwargs: None)
    monkeypatch.setattr(policies, "require_live_paw_lease", lambda *args, **kwargs: leases_checked.append(kwargs["expected_lease_id"]))
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    directory = tmp_path / "trusted"
    directory.mkdir(mode=0o700)
    verifier = directory / "paw-470-issuer.pub"
    verifier.write_bytes(public)
    verifier.chmod(0o600)
    grant = {"assignment_id": "paw-work-b", "wake_id": "wake_" + "a" * 24}
    args = dict(
        authority_dir=directory, assignment_id="paw-work-b", grant=grant,
        expected_sha256=hashlib.sha256(b"old").hexdigest(), replacement="replacement",
        issuer_private_key=private_bytes, trusted_wake_id=grant["wake_id"],
        trusted_presence_generation=1, trusted_lease_generation=1,
        trusted_lease_id="lease-b", lifecycle=object(),
        registry_path=tmp_path / "policy.json", trusted_runtime=object(),
    )
    verifier.unlink()
    with pytest.raises(PawWorktreeBoundaryError, match="public_key_not_provisioned"):
        issue_and_publish_trusted_paw_public_request(**args)
    verifier.write_bytes(b"x" * 32)
    verifier.chmod(0o600)
    with pytest.raises(PawWorktreeBoundaryError, match="public_key_mismatch"):
        issue_and_publish_trusted_paw_public_request(**args)
    verifier.write_bytes(public)
    verifier.chmod(0o600)
    result = issue_and_publish_trusted_paw_public_request(**args)
    assert result.name == trusted_request_filename("paw-work-b")
    import json
    assert verify_paw_public_signature(json.loads(result.read_text()), public_key=public)["grant"] == grant
    # Two rejected attempts each validate admission once; successful publish validates twice.
    assert leases_checked == ["lease-b"] * 4
    with pytest.raises(PawWorktreeBoundaryError, match="already_exists"):
        issue_and_publish_trusted_paw_public_request(**args)


def test_public_verifier_rejects_signed_but_invalid_envelope():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    base = {
        "schema": "agentos.paw-engineering-request/v1",
        "grant": {"assignment_id": "paw-b"},
        "expected_sha256": "a" * 64, "replacement": "ok", "signature": "",
    }
    for mutation in (
        {"schema": "unknown"},
        {"grant": "bad"},
        {"expected_sha256": "not-a-sha"},
        {"replacement": 42},
        {"replacement": "x" * 70000},
    ):
        signed = sign_paw_public_request({**base, **mutation}, private_key=raw)
        with pytest.raises(PawWorktreeBoundaryError):
            verify_paw_public_signature(signed, public_key=public)

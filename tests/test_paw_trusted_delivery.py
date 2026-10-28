from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import agentos_node.paw_trusted_delivery as delivery
from agentos_node.paw_engineering_public_signature import sign_paw_public_request
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def _fixtures(tmp_path):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    dest = tmp_path / "worker"
    dest.mkdir(mode=0o700)
    (dest / "paw-470-issuer.pub").write_bytes(public)
    (dest / "paw-470-issuer.pub").chmod(0o600)
    source = tmp_path / "issuer-signed.json"
    body = {
        "schema": "agentos.paw-engineering-request/v1",
        "grant": {"assignment_id": "paw-b", "wake_id": "wake_" + "a" * 24,
                  "presence_generation": 1, "lease_generation": 2},
        "expected_sha256": "a" * 64, "replacement": "safe", "signature": "",
    }
    import json
    source.write_text(json.dumps(sign_paw_public_request(body, private_key=raw)))
    return source, dest, body


def test_delivery_rejects_untrusted_signature(tmp_path):
    source, dest, body = _fixtures(tmp_path)
    (dest / "paw-470-issuer.pub").write_bytes(b"x" * 32)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_public_signature_invalid"):
        delivery.receive_authorized_paw_request(
            signed_source=source, authority_dir=dest, runtime_root=tmp_path,
            assignment_id="paw-b", lease_id="lease-b", wake_id=body["grant"]["wake_id"],
            presence_generation=1, registry_path=tmp_path / "policy.json",
        )
    assert not (dest / delivery.trusted_request_filename("paw-b")).exists()


def test_delivery_requires_fresh_lease_and_rejects_duplicate(tmp_path, monkeypatch):
    source, dest, body = _fixtures(tmp_path)
    lease = SimpleNamespace(generation=2)
    holder = {"lease": lease}
    class Lifecycle:
        def __init__(self, runtime): pass
        def get_lease(self, assignment_id): return holder["lease"]
    monkeypatch.setattr(delivery, "EmployeeRuntime", lambda root: object())
    monkeypatch.setattr(delivery, "EmployeeLifecycle", Lifecycle)
    monkeypatch.setattr(delivery, "validate_paw_engineering_grant",
                        lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(delivery, "require_canonical_paw_authority", lambda *args, **kwargs: None)
    def check_lease(grant, **kwargs):
        if holder["lease"] is None:
            raise PawWorktreeBoundaryError("paw_live_lease_not_authorized")
    monkeypatch.setattr(delivery, "require_live_paw_lease", check_lease)
    opts = dict(signed_source=source, authority_dir=dest,
                runtime_root=tmp_path, assignment_id="paw-b",
                lease_id="lease-b", wake_id=body["grant"]["wake_id"],
                presence_generation=1, registry_path=tmp_path / "policy.json")
    holder["lease"] = None
    with pytest.raises(PawWorktreeBoundaryError, match="paw_delivery_lease_missing"):
        delivery.receive_authorized_paw_request(**opts)
    holder["lease"] = lease
    output = delivery.receive_authorized_paw_request(**opts)
    assert output.is_file()
    assert output.stat().st_mode & 0o077 == 0
    with pytest.raises(PawWorktreeBoundaryError, match="paw_delivery_already_exists"):
        delivery.receive_authorized_paw_request(**opts)

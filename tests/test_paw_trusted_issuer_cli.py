import json
from types import SimpleNamespace

import pytest

import agentos_node.paw_trusted_issuer_cli as issuer
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def test_issuer_fails_closed_without_private_owner_approval(tmp_path):
    key = tmp_path / "issuer.key"
    key.write_bytes(b"k" * 32)
    key.chmod(0o600)
    approval = tmp_path / "approval.json"
    params = dict(approval_path=approval, private_key_path=key,
                  issuer_outbox=tmp_path, runtime_root=tmp_path,
                  registry_path=tmp_path / "policy.json")
    with pytest.raises(PawWorktreeBoundaryError, match="private_input_missing"):
        issuer.issue_approved_once(**params)
    approval.write_text("{}")
    approval.chmod(0o666)
    with pytest.raises(PawWorktreeBoundaryError, match="private_input_untrusted"):
        issuer.issue_approved_once(**params)


def test_issuer_reuses_existing_trusted_signing_admission(tmp_path, monkeypatch):
    approval = tmp_path / "approval.json"
    key = tmp_path / "issuer.key"
    data = dict(schema="agentos.paw-owner-approved-issuer-request/v1",
                assignment_id="paw-b", lease_id="lease-b",
                wake_id="wake_" + "a" * 24, presence_generation=2,
                lease_generation=3, grant={"work_id": "work-b"},
                expected_sha256="a" * 64, replacement="safe")
    approval.write_text(json.dumps(data))
    approval.chmod(0o600)
    key.write_bytes(b"k" * 32)
    key.chmod(0o600)
    class Runtime:
        def __init__(self, root): self.root = root
    class Lifecycle:
        def __init__(self, runtime): self.runtime = runtime
    monkeypatch.setattr(issuer, "EmployeeRuntime", Runtime)
    monkeypatch.setattr(issuer, "EmployeeLifecycle", Lifecycle)
    recorded = {}
    def publish(**kwargs):
        recorded.update(kwargs)
        return tmp_path / "issued.json"
    monkeypatch.setattr(issuer, "issue_and_publish_trusted_paw_public_request", publish)
    result = issuer.issue_approved_once(
        approval_path=approval, private_key_path=key, issuer_outbox=tmp_path,
        runtime_root=tmp_path, registry_path=tmp_path / "policy.json")
    assert result == tmp_path / "issued.json"
    assert recorded["trusted_lease_id"] == "lease-b"
    assert recorded["trusted_lease_generation"] == 3
    assert recorded["trusted_wake_id"] == data["wake_id"]
    assert recorded["issuer_private_key"] == b"k" * 32

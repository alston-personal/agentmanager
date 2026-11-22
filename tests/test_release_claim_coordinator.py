"""Offline integration tests: trusted-reader composition never performs deployment."""
from datetime import datetime, timedelta, timezone

import pytest

from agent_core.release_claim_coordinator import claim_from_trusted_readers
from agent_core.release_epoch_store import ReleaseFenceError, TargetReleaseEpochStore


NOW = datetime(2026, 11, 22, 7, 0, tzinfo=timezone.utc)
SHA = "b" * 40
DIGEST = "sha256:" + "d" * 64
SCOPE = {"repository": "alston-personal/agentmanager", "realm_id": "realm-test",
         "environment": "offline-test"}


def fixture(tmp_path):
    store = TargetReleaseEpochStore(tmp_path / "epoch.sqlite3")
    store.initialize_from_verified_readback(
        **SCOPE, installed_sha="a" * 40, installed_epoch=3)
    request = {**SCOPE, "project_id": "agentos-core",
               "operation": "runtime.converge", "source_ref": "main",
               "source_commit": SHA, "artifact_digest": DIGEST,
               "approval_receipt_id": "one-receipt-4", "release_epoch": 4}
    intent = {**request, "schema": "agentos.approved-release-intent/v1",
              "state": "approved", "authorized_principal": "trusted-issuer",
              "expires_at": (NOW + timedelta(minutes=5)).isoformat()}
    return store, request, intent


def claim(store, request, intent, *, principal="trusted-issuer"):
    return claim_from_trusted_readers(
        request=request, intent_reader=lambda _request: intent,
        principal_reader=lambda: principal, target_store=store, now=NOW)


def test_trusted_reader_claim_uses_durable_target_epoch(tmp_path):
    store, request, intent = fixture(tmp_path)
    request["observed_target"] = {**SCOPE, "release_epoch": 0}
    token = claim(store, request, intent)
    assert len(token) == 64
    assert store.inspect(**SCOPE)["pending_epoch"] == 4
    with pytest.raises(ReleaseFenceError, match="release_pending_requires_operator_recovery"):
        claim(store, request, intent)


@pytest.mark.parametrize("tamper,reason", [
    ({"source_commit": "c" * 40}, "source_commit_not_approved"),
    ({"artifact_digest": "sha256:" + "e" * 64}, "artifact_digest_not_approved"),
    ({"approval_receipt_id": "forged"}, "approval_receipt_mismatch"),
    ({"realm_id": "other-realm"}, "target_not_initialized"),
    ({"source_ref": "core/integration"}, "non_main_source_forbidden"),
    ({"release_epoch": 3}, "request_epoch_mismatch"),
])
def test_untrusted_request_cannot_override_trusted_intent(tmp_path, tamper, reason):
    store, request, intent = fixture(tmp_path)
    request.update(tamper)
    with pytest.raises(ReleaseFenceError, match=reason):
        claim(store, request, intent)
    assert store.inspect(**SCOPE)["pending_epoch"] is None


def test_missing_or_failed_reader_is_denied(tmp_path):
    store, request, intent = fixture(tmp_path)
    with pytest.raises(ReleaseFenceError, match="trusted_release_adapter_missing"):
        claim_from_trusted_readers(
            request=request, intent_reader=None,
            principal_reader=lambda: "trusted-issuer", target_store=store, now=NOW)
    with pytest.raises(ReleaseFenceError, match="trusted_release_reader_unavailable"):
        claim_from_trusted_readers(
            request=request,
            intent_reader=lambda _: (_ for _ in ()).throw(RuntimeError("network")),
            principal_reader=lambda: "trusted-issuer", target_store=store, now=NOW)
    with pytest.raises(ReleaseFenceError, match="missing_trusted_release_intent"):
        claim_from_trusted_readers(
            request=request, intent_reader=lambda _: None,
            principal_reader=lambda: "trusted-issuer", target_store=store, now=NOW)
    with pytest.raises(ReleaseFenceError, match="principal_not_authorized"):
        claim(store, request, intent, principal="old-executor")
    assert store.inspect(**SCOPE)["pending_epoch"] is None

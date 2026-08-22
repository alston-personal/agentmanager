from datetime import datetime, timezone

import pytest

from agent_core.enrollment_store import EnrollmentError, EnrollmentStore
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinReference


def _claim(enrollment_id: str) -> EnrollmentClaim:
    return EnrollmentClaim(
        enrollment_id=enrollment_id,
        node_public_key="pubkey-test",
        device_fingerprint="device-fingerprint",
        hostname="node-test",
        platform="linux",
        arch="aarch64",
        requested_profile="edge",
    )


def test_enrollment_secret_is_single_use_and_not_stored_raw(tmp_path) -> None:
    store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
    )
    envelope, secret = store.issue(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
    )
    claim = _claim(envelope.enrollment_id)
    assert store.claim(envelope=envelope, secret=secret, claim=claim) == claim.claim_id
    with pytest.raises(EnrollmentError, match="already consumed"):
        store.claim(envelope=envelope, secret=secret, claim=claim)

    raw = (tmp_path / "enrollment.db").read_bytes()
    assert secret.encode() not in raw


def test_join_reference_is_small_one_touch_transport_resolved_by_core(tmp_path) -> None:
    store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
    )
    reference = store.issue_reference(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
    )
    assert isinstance(reference, JoinReference)
    assert reference.link().startswith("https://core.example.test/join#AGENTOSREF1.")

    decoded = JoinReference.decode(reference.link())
    ticket = store.resolve(decoded)
    assert ticket.envelope.enrollment_id == reference.enrollment_id
    assert ticket.envelope.realm_id == "realm-personal"
    assert ticket.secret == reference.secret


def test_reference_resolution_rejects_wrong_core_or_secret(tmp_path) -> None:
    store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
    )
    reference = store.issue_reference(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
    )
    with pytest.raises(EnrollmentError, match="invalid enrollment secret"):
        store.resolve(JoinReference(reference.core_url, reference.enrollment_id, "wrong"))
    with pytest.raises(EnrollmentError, match="Core does not match"):
        store.resolve(JoinReference("https://other.example.test", reference.enrollment_id, reference.secret))


def test_enrollment_rejects_wrong_secret_and_expiry(tmp_path) -> None:
    current = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
    store = EnrollmentStore(str(tmp_path / "enrollment.db"), now=lambda: current)
    envelope, secret = store.issue(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T09:30:00Z",
    )
    with pytest.raises(EnrollmentError, match="invalid enrollment secret"):
        store.claim(envelope=envelope, secret="wrong", claim=_claim(envelope.enrollment_id))

    expired_store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(EnrollmentError, match="expired"):
        expired_store.claim(envelope=envelope, secret=secret, claim=_claim(envelope.enrollment_id))

from datetime import datetime, timezone

from agent_core.enrollment_service import EnrollmentService
from agent_core.enrollment_store import EnrollmentStore
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinTicket, NodeLifecycle


def test_claim_establishes_stable_identity_but_not_active_authority(tmp_path) -> None:
    store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
    )
    envelope, secret = store.issue(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
    )
    claim = EnrollmentClaim(
        enrollment_id=envelope.enrollment_id,
        node_public_key="pubkey-test",
        device_fingerprint="fingerprint-test",
        hostname="camera-01",
        platform="linux",
        arch="aarch64",
        requested_profile="edge",
    )
    receipt = EnrollmentService(store).claim(
        JoinTicket(envelope=envelope, secret=secret),
        claim,
        observed_at="2026-08-22T09:00:01Z",
    )

    assert receipt.node_identity.node_id.startswith("node_")
    assert receipt.node_identity.realm_id == "realm-personal"
    assert receipt.checkpoint.lifecycle is NodeLifecycle.IDENTIFIED
    assert receipt.checkpoint.identity_id == receipt.node_identity.identity_id
    assert receipt.checkpoint.capability_manifest_id is None
    assert receipt.checkpoint.governance_ref is None

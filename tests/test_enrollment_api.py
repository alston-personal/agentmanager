from datetime import datetime, timezone

from agent_core.enrollment_api import EnrollmentApi
from agent_core.enrollment_store import EnrollmentStore
from runtime_core.onboarding_v1 import EnrollmentClaim


def test_resolve_then_claim_one_touch_reference(tmp_path) -> None:
    store = EnrollmentStore(
        str(tmp_path / "enrollment.db"),
        now=lambda: datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
    )
    reference = store.issue_reference(
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
    )
    api = EnrollmentApi(store=store)

    resolved = api.resolve({"reference": reference.code()})
    assert resolved["realm_id"] == "realm-personal"
    assert resolved["bootstrap_policy"]["allow_external_effects"] is False

    claim = EnrollmentClaim(
        enrollment_id=reference.enrollment_id,
        node_public_key="ssh-ed25519 AAAATEST agentos-node",
        device_fingerprint="dev_test",
        hostname="camera-01",
        platform="linux",
        arch="aarch64",
        requested_profile="edge",
    )
    response = api.claim(
        {"ticket": resolved["ticket"], "claim": claim.__dict__},
        observed_at="2026-08-22T09:00:01Z",
    )
    assert response["node_identity"]["node_id"].startswith("node_")
    assert response["checkpoint"]["lifecycle"] == "identified"
    assert response["checkpoint"]["governance_ref"] is None

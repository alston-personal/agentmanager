from pathlib import Path

import pytest

from agentos_node.enrollment_client import enroll_node
from runtime_core.onboarding_v1 import JoinEnvelope, JoinReference, JoinTicket


class FakeTransport:
    def __init__(self, reference: JoinReference, *, change_core: bool = False) -> None:
        core = "https://evil.example.test" if change_core else reference.core_url
        self.ticket = JoinTicket(
            envelope=JoinEnvelope(
                enrollment_id=reference.enrollment_id,
                realm_id="realm-personal",
                core_url=core,
                expires_at="2026-08-22T10:00:00Z",
                nonce="nonce-test",
            ),
            secret=reference.secret,
        )
        self.claim_payload = None

    def resolve(self, reference: JoinReference) -> dict[str, object]:
        return {"ticket": self.ticket.encode()}

    def claim(self, core_url: str, payload: dict[str, object]) -> dict[str, object]:
        self.claim_payload = payload
        return {
            "schema": "agentos.enrollment-claim-response/v1",
            "node_identity": {"node_id": "node_test"},
            "checkpoint": {"lifecycle": "identified"},
        }


def _identity_dir(tmp_path: Path) -> Path:
    private_key = tmp_path / "identity_ed25519"
    public_key = tmp_path / "identity_ed25519.pub"
    private_key.write_text("PRIVATE\n", encoding="utf-8")
    public_key.write_text("ssh-ed25519 AAAATEST agentos-node\n", encoding="utf-8")
    return tmp_path


def test_enrollment_client_binds_resolved_ticket_to_reference_core(tmp_path) -> None:
    reference = JoinReference("https://core.example.test", "enr_test", "secret-test")
    transport = FakeTransport(reference)
    response = enroll_node(reference.link(), transport=transport, identity_dir=_identity_dir(tmp_path))
    assert response["checkpoint"]["lifecycle"] == "identified"
    assert transport.claim_payload["claim"]["node_public_key"].startswith("ssh-ed25519 ")
    assert "PRIVATE" not in repr(transport.claim_payload)


def test_enrollment_client_refuses_core_origin_switch(tmp_path) -> None:
    reference = JoinReference("https://core.example.test", "enr_test", "secret-test")
    with pytest.raises(PermissionError, match="change Core origin"):
        enroll_node(reference.code(), transport=FakeTransport(reference, change_core=True), identity_dir=_identity_dir(tmp_path))

import pytest

from runtime_core.onboarding_v1 import (
    BootstrapPolicy,
    JoinEnvelope,
    JoinTicket,
    NodeLifecycle,
    validate_transition,
)


def test_join_code_round_trip_preserves_fail_closed_bootstrap_policy() -> None:
    envelope = JoinEnvelope(
        enrollment_id="enr_test",
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
        nonce="nonce-test",
        bootstrap_policy=BootstrapPolicy(profile="edge", requested_capabilities=("node.status",)),
    )
    decoded = JoinEnvelope.decode(envelope.encode())
    assert decoded == envelope
    assert decoded.bootstrap_policy.allow_external_effects is False


def test_join_ticket_round_trip_contains_one_short_lived_bearer_artifact() -> None:
    envelope = JoinEnvelope(
        enrollment_id="enr_test",
        realm_id="realm-personal",
        core_url="https://core.example.test",
        expires_at="2026-08-22T10:00:00Z",
        nonce="nonce-test",
    )
    ticket = JoinTicket(envelope=envelope, secret="temporary-secret")
    encoded = ticket.encode()
    assert encoded.startswith("AGENTOSJOIN1.")
    assert JoinTicket.decode(encoded) == ticket


def test_bootstrap_policy_cannot_grant_external_effects() -> None:
    with pytest.raises(ValueError, match="may not grant external effects"):
        BootstrapPolicy(allow_external_effects=True)


def test_join_requires_https_except_localhost_development() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        JoinEnvelope("enr", "realm", "http://example.test", "2026-08-22T10:00:00Z", "nonce")

    JoinEnvelope("enr", "realm", "http://127.0.0.1:8765", "2026-08-22T10:00:00Z", "nonce")


def test_lifecycle_cannot_skip_governance_before_active() -> None:
    validate_transition(NodeLifecycle.REGISTERED, NodeLifecycle.GOVERNED)
    validate_transition(NodeLifecycle.GOVERNED, NodeLifecycle.ACTIVE)
    with pytest.raises(ValueError, match="invalid Node lifecycle transition"):
        validate_transition(NodeLifecycle.REGISTERED, NodeLifecycle.ACTIVE)

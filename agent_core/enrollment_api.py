"""Transport-neutral handlers for AgentOS Node enrollment APIs.

HTTP/WebSocket adapters may expose these handlers, but protocol semantics live
here so enrollment is testable without a network stack.
"""

from __future__ import annotations

from dataclasses import asdict

from agent_core.enrollment_service import EnrollmentService
from agent_core.enrollment_store import EnrollmentStore
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinReference, JoinTicket


class EnrollmentApi:
    def __init__(self, *, store: EnrollmentStore, service: EnrollmentService | None = None) -> None:
        self.store = store
        self.service = service or EnrollmentService(store)

    def resolve(self, payload: dict[str, object]) -> dict[str, object]:
        raw_reference = str(payload.get("reference", ""))
        reference = JoinReference.decode(raw_reference)
        ticket = self.store.resolve(reference)
        envelope = ticket.envelope
        return {
            "schema": "agentos.enrollment-resolve-response/v1",
            "ticket": ticket.encode(),
            "realm_id": envelope.realm_id,
            "core_url": envelope.core_url,
            "expires_at": envelope.expires_at,
            "bootstrap_policy": asdict(envelope.bootstrap_policy),
        }

    def claim(self, payload: dict[str, object], *, observed_at: str) -> dict[str, object]:
        ticket = JoinTicket.decode(str(payload.get("ticket", "")))
        claim_payload = payload.get("claim")
        if not isinstance(claim_payload, dict):
            raise ValueError("claim payload is required")
        claim = EnrollmentClaim(**claim_payload)
        receipt = self.service.claim(ticket, claim, observed_at=observed_at)
        return {
            "schema": "agentos.enrollment-claim-response/v1",
            "claim_id": receipt.claim_id,
            "node_identity": asdict(receipt.node_identity),
            "checkpoint": {
                **asdict(receipt.checkpoint),
                "lifecycle": receipt.checkpoint.lifecycle.value,
            },
        }

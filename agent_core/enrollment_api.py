"""Transport-neutral handlers for AgentOS Node enrollment APIs.

HTTP/WebSocket adapters may expose these handlers, but protocol semantics live
here so enrollment is testable without a network stack.
"""

from __future__ import annotations

from dataclasses import asdict

from agent_core.bootstrap_session_store import BootstrapSessionStore
from agent_core.enrollment_service import EnrollmentService
from agent_core.enrollment_store import EnrollmentStore
from agent_core.node_directory_store import NodeDirectoryStore
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinReference, JoinTicket, NodeLifecycle


class EnrollmentApi:
    def __init__(
        self,
        *,
        store: EnrollmentStore,
        service: EnrollmentService | None = None,
        directory: NodeDirectoryStore | None = None,
        bootstrap_sessions: BootstrapSessionStore | None = None,
    ) -> None:
        self.store = store
        self.service = service or EnrollmentService(store)
        self.directory = directory
        self.bootstrap_sessions = bootstrap_sessions

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

        if self.directory is not None:
            current = self.directory.checkpoint(receipt.node_identity.node_id)
            if current is None:
                self.directory.initialize_node(receipt.checkpoint)
            elif current.lifecycle is NodeLifecycle.REVOKED:
                raise PermissionError("revoked Node cannot re-enroll itself")

        response: dict[str, object] = {
            "schema": "agentos.enrollment-claim-response/v1",
            "claim_id": receipt.claim_id,
            "node_identity": asdict(receipt.node_identity),
            "checkpoint": {
                **asdict(receipt.checkpoint),
                "lifecycle": receipt.checkpoint.lifecycle.value,
            },
        }
        if self.bootstrap_sessions is not None:
            session_id, token, expires_at = self.bootstrap_sessions.issue(node_id=receipt.node_identity.node_id)
            response["bootstrap_session"] = {
                "schema": "agentos.bootstrap-session/v1",
                "session_id": session_id,
                "token": token,
                "scope": "onboarding.submit",
                "expires_at": expires_at,
            }
        return response

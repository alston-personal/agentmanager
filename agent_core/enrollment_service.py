"""Core-side AgentOS Node enrollment claim service.

Successful claim proves possession of a one-time Join Ticket and establishes a
stable Node identity.  It does not authorize discovered capabilities and does
not activate the Node.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from agent_core.enrollment_store import EnrollmentStore
from runtime_core.node_v1 import NodeIdentity
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinTicket, NodeLifecycle, OnboardingCheckpoint


@dataclass(frozen=True)
class EnrollmentReceipt:
    node_identity: NodeIdentity
    claim_id: str
    checkpoint: OnboardingCheckpoint


def derive_node_id(*, realm_id: str, node_public_key: str, device_fingerprint: str) -> str:
    material = f"{realm_id}\x00{node_public_key}\x00{device_fingerprint}".encode("utf-8")
    return "node_" + sha256(material).hexdigest()[:32]


class EnrollmentService:
    def __init__(self, store: EnrollmentStore) -> None:
        self.store = store

    def claim(self, ticket: JoinTicket, claim: EnrollmentClaim, *, observed_at: str) -> EnrollmentReceipt:
        if claim.requested_profile != ticket.envelope.bootstrap_policy.profile:
            raise PermissionError("Node requested a profile different from bootstrap policy")
        claim_id = self.store.claim(envelope=ticket.envelope, secret=ticket.secret, claim=claim)
        node_id = derive_node_id(
            realm_id=ticket.envelope.realm_id,
            node_public_key=claim.node_public_key,
            device_fingerprint=claim.device_fingerprint,
        )
        identity = NodeIdentity(
            node_id=node_id,
            realm_id=ticket.envelope.realm_id,
            hostname=claim.hostname,
            platform=claim.platform,
            arch=claim.arch,
            profile=claim.requested_profile,
        )
        checkpoint = OnboardingCheckpoint(
            node_id=node_id,
            lifecycle=NodeLifecycle.IDENTIFIED,
            observed_at=observed_at,
            identity_id=identity.identity_id,
        )
        return EnrollmentReceipt(node_identity=identity, claim_id=claim_id, checkpoint=checkpoint)

"""Portable AgentOS Node onboarding contracts.

The human establishes trust once; AgentOS performs the rest. Join material is
short-lived and single-use. Discovery never implies authority, and onboarding
cannot silently activate a Node before governance has accepted its capabilities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import base64
import json
from typing import Any


ONBOARDING_SCHEMA = "agentos.node-onboarding/v1"
JOIN_SCHEMA = "agentos.join/v1"
JOIN_TICKET_SCHEMA = "agentos.join-ticket/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _content_id(prefix: str, value: Any) -> str:
    return prefix + sha256(_canonical(value).encode("utf-8")).hexdigest()[:32]


def _encode_payload(prefix: str, payload: dict[str, Any]) -> str:
    raw = _canonical(payload).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{prefix}.{token}"


def _decode_payload(prefix: str, value: str) -> dict[str, Any]:
    if not value.startswith(prefix + "."):
        raise ValueError("unsupported AgentOS join code")
    token = value.split(".", 1)[1]
    token += "=" * (-len(token) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - boundary parser must fail closed
        raise ValueError("invalid AgentOS join code") from exc


class NodeLifecycle(str, Enum):
    UNSEEN = "unseen"
    BOOTSTRAPPED = "bootstrapped"
    IDENTIFIED = "identified"
    DISCOVERED = "discovered"
    RECONCILED = "reconciled"
    REGISTERED = "registered"
    GOVERNED = "governed"
    ACTIVE = "active"
    OFFLINE = "offline"
    REVOKED = "revoked"


_ALLOWED_TRANSITIONS: dict[NodeLifecycle, set[NodeLifecycle]] = {
    NodeLifecycle.UNSEEN: {NodeLifecycle.BOOTSTRAPPED, NodeLifecycle.REVOKED},
    NodeLifecycle.BOOTSTRAPPED: {NodeLifecycle.IDENTIFIED, NodeLifecycle.REVOKED},
    NodeLifecycle.IDENTIFIED: {NodeLifecycle.DISCOVERED, NodeLifecycle.REVOKED},
    NodeLifecycle.DISCOVERED: {NodeLifecycle.RECONCILED, NodeLifecycle.REGISTERED, NodeLifecycle.REVOKED},
    NodeLifecycle.RECONCILED: {NodeLifecycle.REGISTERED, NodeLifecycle.REVOKED},
    NodeLifecycle.REGISTERED: {NodeLifecycle.GOVERNED, NodeLifecycle.REVOKED},
    NodeLifecycle.GOVERNED: {NodeLifecycle.ACTIVE, NodeLifecycle.REVOKED},
    NodeLifecycle.ACTIVE: {NodeLifecycle.OFFLINE, NodeLifecycle.DISCOVERED, NodeLifecycle.REVOKED},
    NodeLifecycle.OFFLINE: {NodeLifecycle.DISCOVERED, NodeLifecycle.REVOKED},
    NodeLifecycle.REVOKED: set(),
}


def validate_transition(before: NodeLifecycle, after: NodeLifecycle) -> None:
    if after not in _ALLOWED_TRANSITIONS[before]:
        raise ValueError(f"invalid Node lifecycle transition: {before.value} -> {after.value}")


@dataclass(frozen=True)
class BootstrapPolicy:
    profile: str = "edge"
    allow_discovery: bool = True
    allow_local_reconciliation_scan: bool = True
    allow_external_effects: bool = False
    requested_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.profile.strip():
            raise ValueError("bootstrap profile is required")
        if self.allow_external_effects:
            raise ValueError("bootstrap policy may not grant external effects")


@dataclass(frozen=True)
class JoinEnvelope:
    enrollment_id: str
    realm_id: str
    core_url: str
    expires_at: str
    nonce: str
    bootstrap_policy: BootstrapPolicy = field(default_factory=BootstrapPolicy)
    issuer: str = "agentos-core"
    schema_version: str = JOIN_SCHEMA

    def __post_init__(self) -> None:
        required = (self.enrollment_id, self.realm_id, self.core_url, self.expires_at, self.nonce, self.issuer)
        if any(not value.strip() for value in required):
            raise ValueError("join envelope identity fields are required")
        if not (self.core_url.startswith("https://") or self.core_url.startswith("http://127.0.0.1")):
            raise ValueError("join core_url must use HTTPS except for localhost development")

    @property
    def envelope_id(self) -> str:
        return _content_id("join_", asdict(self))

    def encode(self) -> str:
        return _encode_payload("AGENTOS1", asdict(self))

    @classmethod
    def decode(cls, value: str) -> "JoinEnvelope":
        payload = _decode_payload("AGENTOS1", value)
        policy_payload = payload.pop("bootstrap_policy", {})
        if "requested_capabilities" in policy_payload:
            policy_payload["requested_capabilities"] = tuple(policy_payload["requested_capabilities"])
        policy = BootstrapPolicy(**policy_payload)
        return cls(bootstrap_policy=policy, **payload)


@dataclass(frozen=True)
class JoinTicket:
    """Short-lived bearer ticket suitable for QR, link, NFC or one-line CLI.

    The secret is intentionally present in the transport ticket because the
    human needs only one artifact to join a device. Core persists only its hash.
    The ticket must therefore be treated like a temporary password and consumed
    once; it must never be written to logs or durable Node state.
    """

    envelope: JoinEnvelope
    secret: str
    schema_version: str = JOIN_TICKET_SCHEMA

    def __post_init__(self) -> None:
        if not self.secret.strip():
            raise ValueError("join ticket secret is required")

    def encode(self) -> str:
        return _encode_payload(
            "AGENTOSJOIN1",
            {
                "schema_version": self.schema_version,
                "envelope": asdict(self.envelope),
                "secret": self.secret,
            },
        )

    @classmethod
    def decode(cls, value: str) -> "JoinTicket":
        payload = _decode_payload("AGENTOSJOIN1", value)
        if payload.get("schema_version") != JOIN_TICKET_SCHEMA:
            raise ValueError("unsupported AgentOS join ticket schema")
        envelope_payload = payload["envelope"]
        policy_payload = envelope_payload.pop("bootstrap_policy", {})
        if "requested_capabilities" in policy_payload:
            policy_payload["requested_capabilities"] = tuple(policy_payload["requested_capabilities"])
        envelope = JoinEnvelope(bootstrap_policy=BootstrapPolicy(**policy_payload), **envelope_payload)
        return cls(envelope=envelope, secret=payload["secret"])


@dataclass(frozen=True)
class EnrollmentClaim:
    enrollment_id: str
    node_public_key: str
    device_fingerprint: str
    hostname: str
    platform: str
    arch: str
    requested_profile: str

    def __post_init__(self) -> None:
        required = (
            self.enrollment_id,
            self.node_public_key,
            self.device_fingerprint,
            self.hostname,
            self.platform,
            self.arch,
            self.requested_profile,
        )
        if any(not value.strip() for value in required):
            raise ValueError("enrollment claim fields are required")

    @property
    def claim_id(self) -> str:
        return _content_id("claim_", asdict(self))


@dataclass(frozen=True)
class OnboardingCheckpoint:
    node_id: str
    lifecycle: NodeLifecycle
    observed_at: str
    identity_id: str | None = None
    capability_manifest_id: str | None = None
    reconciliation_plan_id: str | None = None
    governance_ref: str | None = None
    schema_version: str = ONBOARDING_SCHEMA

    @property
    def checkpoint_id(self) -> str:
        return _content_id("onboard_", asdict(self))

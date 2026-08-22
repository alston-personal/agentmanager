"""Node-side client for one-touch AgentOS enrollment."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Protocol
from urllib import request

from agentos_node.capability_discovery import discover_capabilities_for_identity
from agentos_node.local_cognition_discovery import discover_local_cognition
from agentos_node.node_identity import ensure_node_identity
from runtime_core.node_v1 import NodeIdentity
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinReference, JoinTicket


class EnrollmentTransport(Protocol):
    def resolve(self, reference: JoinReference) -> dict[str, object]: ...
    def claim(self, core_url: str, payload: dict[str, object]) -> dict[str, object]: ...
    def submit_onboarding(self, core_url: str, payload: dict[str, object]) -> dict[str, object]: ...


class HttpEnrollmentTransport:
    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def _post(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:  # noqa: S310 - trusted Core URL validated by JoinReference
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid enrollment response")
        return data

    def resolve(self, reference: JoinReference) -> dict[str, object]:
        return self._post(reference.core_url.rstrip("/") + "/v1/nodes/enrollment/resolve", {"reference": reference.code()})

    def claim(self, core_url: str, payload: dict[str, object]) -> dict[str, object]:
        return self._post(core_url.rstrip("/") + "/v1/nodes/enrollment/claim", payload)

    def submit_onboarding(self, core_url: str, payload: dict[str, object]) -> dict[str, object]:
        return self._post(core_url.rstrip("/") + "/v1/nodes/onboarding/submit", payload)


def _claimed_identity(response: dict[str, object]) -> NodeIdentity:
    raw = response.get("node_identity")
    if not isinstance(raw, dict):
        raise ValueError("enrollment claim response did not include node_identity")
    data = dict(raw)
    data["labels"] = tuple(data.get("labels", ()))
    return NodeIdentity(**data)


def enroll_node(
    reference_value: str,
    *,
    transport: EnrollmentTransport | None = None,
    identity_dir: Path | None = None,
    cognition_roots: Iterable[Path] | None = None,
) -> dict[str, object]:
    """Claim identity and, when Core supports it, finish metadata onboarding.

    Bootstrap session material remains in memory only and is intentionally
    omitted from the returned receipt so CLI/telemetry cannot accidentally log
    it. Older Core implementations without bootstrap sessions still stop safely
    at IDENTIFIED.
    """

    reference = JoinReference.decode(reference_value)
    channel = transport or HttpEnrollmentTransport()
    resolved = channel.resolve(reference)
    ticket = JoinTicket.decode(str(resolved.get("ticket", "")))

    # Never follow an enrollment response to a different Core origin.
    if ticket.envelope.core_url != reference.core_url:
        raise PermissionError("resolved enrollment attempted to change Core origin")
    if ticket.envelope.enrollment_id != reference.enrollment_id:
        raise PermissionError("resolved enrollment_id does not match Join Reference")
    if ticket.secret != reference.secret:
        raise PermissionError("resolved ticket secret does not match Join Reference")

    local = ensure_node_identity(identity_dir)
    claim = EnrollmentClaim(
        enrollment_id=ticket.envelope.enrollment_id,
        node_public_key=local.public_key,
        device_fingerprint=local.device_fingerprint,
        hostname=local.hostname,
        platform=local.platform,
        arch=local.arch,
        requested_profile=ticket.envelope.bootstrap_policy.profile,
    )
    claim_response = channel.claim(
        reference.core_url,
        {"ticket": ticket.encode(), "claim": asdict(claim)},
    )
    if str(claim_response.get("schema", "")) != "agentos.enrollment-claim-response/v1":
        raise ValueError("unexpected enrollment claim response schema")

    bootstrap = claim_response.get("bootstrap_session")
    if not isinstance(bootstrap, dict):
        # Backward-compatible safe boundary: identity exists, no authority was
        # granted, and no secret is added to the returned receipt.
        return {key: value for key, value in claim_response.items() if key != "bootstrap_session"}
    if bootstrap.get("scope") != "onboarding.submit" or not str(bootstrap.get("token", "")).strip():
        raise PermissionError("Core returned an invalid bootstrap onboarding session")

    identity = _claimed_identity(claim_response)
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = discover_capabilities_for_identity(identity, observed_at=observed_at)

    roots = tuple(cognition_roots) if cognition_roots is not None else (Path.home() / ".agentos" / "cognition",)
    descriptors = discover_local_cognition(roots)
    onboarding_response = channel.submit_onboarding(
        reference.core_url,
        {
            "bootstrap_token": str(bootstrap["token"]),
            "manifest": asdict(manifest),
            "local_cognition": [asdict(item) for item in descriptors],
        },
    )
    if str(onboarding_response.get("schema", "")) != "agentos.onboarding-submit-response/v1":
        raise ValueError("unexpected onboarding submission response schema")

    return {
        "schema": "agentos.enrollment-complete-response/v1",
        "claim_id": claim_response.get("claim_id"),
        "node_identity": claim_response.get("node_identity"),
        "checkpoint": claim_response.get("checkpoint"),
        "onboarding": onboarding_response,
    }

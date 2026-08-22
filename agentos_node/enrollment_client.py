"""Node-side client for one-touch AgentOS enrollment."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Protocol
from urllib import request

from agentos_node.node_identity import ensure_node_identity
from runtime_core.onboarding_v1 import EnrollmentClaim, JoinReference, JoinTicket


class EnrollmentTransport(Protocol):
    def resolve(self, reference: JoinReference) -> dict[str, object]: ...
    def claim(self, core_url: str, payload: dict[str, object]) -> dict[str, object]: ...


class HttpEnrollmentTransport:
    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def _post(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
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


def enroll_node(
    reference_value: str,
    *,
    transport: EnrollmentTransport | None = None,
    identity_dir: Path | None = None,
) -> dict[str, object]:
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
    response = channel.claim(
        reference.core_url,
        {"ticket": ticket.encode(), "claim": asdict(claim)},
    )
    if str(response.get("schema", "")) != "agentos.enrollment-claim-response/v1":
        raise ValueError("unexpected enrollment claim response schema")
    return response

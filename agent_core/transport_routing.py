"""Authority-driven transport routing for AgentOS control and workflow intents.

This module deliberately does not classify natural-language prompts. Callers must
supply a typed intent class. The resolver's job is narrower and security-relevant:
choose only among transports already authorized for that class and fail closed
when none are available.

In particular, GitHub Actions is never a generic fallback for AgentOS control-plane
work. A transport failure does not expand authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_PATH = ROOT / "governance" / "transport-routing.json"


class TransportRoutingError(RuntimeError):
    """Base class for transport-routing failures."""


class UnknownIntentClass(TransportRoutingError):
    """Raised when the caller supplies an undeclared intent class."""


class UnauthorizedTransport(TransportRoutingError):
    """Raised when a requested transport lacks authority for the intent class."""


class TransportUnavailable(TransportRoutingError):
    """Raised when no authorized transport is currently available."""


@dataclass(frozen=True)
class RouteDecision:
    intent_class: str
    transport: str
    authority: str
    policy_id: str


def load_policy(path: Path | str = DEFAULT_POLICY_PATH) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        policy = json.load(handle)
    if policy.get("schema") != "agentos.transport-routing/v1":
        raise TransportRoutingError("unsupported transport-routing policy schema")
    return policy


def _available_set(available_transports: Iterable[str] | Mapping[str, bool]) -> set[str]:
    if isinstance(available_transports, Mapping):
        return {name for name, available in available_transports.items() if available}
    return set(available_transports)


def resolve_transport(
    intent_class: str,
    available_transports: Iterable[str] | Mapping[str, bool],
    *,
    requested_transport: str | None = None,
    policy: dict | None = None,
) -> RouteDecision:
    """Resolve one authorized transport deterministically.

    `intent_class` must already be typed by the caller (currently `control_plane`
    or `workflow`). `available_transports` is only a liveness/capability snapshot;
    it never grants authority.

    If `requested_transport` is supplied it is still checked against the declared
    allowlist. This prevents a caller from forcing GitHub Actions for a control-plane
    intent merely because an Actions runner is reachable.
    """

    active_policy = policy or load_policy()
    intent = active_policy.get("intent_classes", {}).get(intent_class)
    if intent is None:
        raise UnknownIntentClass(f"unknown intent class: {intent_class}")

    allowed = tuple(intent.get("allowed_transports", ()))
    available = _available_set(available_transports)

    if requested_transport is not None:
        if requested_transport not in allowed:
            raise UnauthorizedTransport(
                f"transport {requested_transport!r} is not authorized for intent class {intent_class!r}"
            )
        if requested_transport not in available:
            raise TransportUnavailable(
                f"authorized transport {requested_transport!r} is unavailable for intent class {intent_class!r}"
            )
        selected = requested_transport
    else:
        priority = active_policy.get("transport_priority", ())
        selected = next(
            (transport for transport in priority if transport in allowed and transport in available),
            None,
        )
        if selected is None:
            raise TransportUnavailable(
                f"no authorized transport available for intent class {intent_class!r}; "
                "authority is not expanded by fallback"
            )

    transport = active_policy.get("transports", {}).get(selected)
    if not transport:
        raise TransportRoutingError(f"selected transport is undeclared: {selected}")

    return RouteDecision(
        intent_class=intent_class,
        transport=selected,
        authority=str(transport.get("authority", "unknown")),
        policy_id=str(active_policy.get("policy_id", "unknown")),
    )

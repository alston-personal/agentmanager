from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


REDISCOVERY_REASONS = (
    "missing",
    "stale",
    "deeper",
    "expanded_scope",
    "conflict",
    "stronger_evidence",
)

_DEPTH_RANK = {"summary": 0, "structural": 1, "implementation": 2, "runtime": 3}
_EVIDENCE_RANK = {"declared": 0, "documented": 1, "observed": 2, "verified": 3, "receipt": 4}
_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "secret",
    "bearer",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rank(value: str | None, table: Mapping[str, int]) -> int:
    return table.get(str(value or "").strip().lower(), -1)


def sanitize_url(value: str) -> str:
    """Remove credential-bearing URL userinfo while preserving normal locators."""
    text = str(value or "")
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc or "@" not in parts.netloc:
        return text
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def sanitize_for_persistence(value: Any, *, key: str | None = None) -> Any:
    """Recursively sanitize data before it is written to IR/project/runtime state."""
    if key and key.casefold() in _SENSITIVE_KEYS:
        return "[REDACTED]" if value not in (None, "") else value
    if isinstance(value, dict):
        return {k: sanitize_for_persistence(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_persistence(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_persistence(item) for item in value)
    if isinstance(value, str):
        return sanitize_url(value)
    return value


@dataclass(frozen=True)
class DiscoveryRequirement:
    fact_key: str
    scope: str
    depth: str = "summary"
    evidence_strength: str = "documented"
    require_fresh: bool = True


@dataclass(frozen=True)
class KnownFact:
    fact_key: str
    value: Any
    scope: str
    depth: str = "summary"
    evidence_strength: str = "documented"
    freshness: str = "fresh"
    conflicting: bool = False
    source: str | None = None
    verified_at: str | None = None


def assess_requirement(required: DiscoveryRequirement, known: KnownFact | None) -> dict[str, Any]:
    """Decide whether a known fact can be reused or targeted rediscovery is justified."""
    reasons: list[str] = []
    if known is None or known.value in (None, ""):
        reasons.append("missing")
    else:
        if known.scope != required.scope:
            reasons.append("expanded_scope")
        if known.conflicting:
            reasons.append("conflict")
        if required.require_fresh and known.freshness not in {"fresh", "static"}:
            reasons.append("stale")
        if _rank(known.depth, _DEPTH_RANK) < _rank(required.depth, _DEPTH_RANK):
            reasons.append("deeper")
        if _rank(known.evidence_strength, _EVIDENCE_RANK) < _rank(required.evidence_strength, _EVIDENCE_RANK):
            reasons.append("stronger_evidence")

    # Preserve stable machine ordering for receipts/tests.
    ordered = [reason for reason in REDISCOVERY_REASONS if reason in reasons]
    return {
        "fact_key": required.fact_key,
        "decision": "reuse" if not ordered else "rediscover",
        "reusable": not ordered,
        "rediscovery_reasons": ordered,
        "known": sanitize_for_persistence(known.__dict__) if known is not None else None,
        "required": required.__dict__,
    }


def build_discovery_receipt(
    assessments: list[dict[str, Any]],
    *,
    project_id: str | None = None,
    promoted: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rediscovered = [item["fact_key"] for item in assessments if not item.get("reusable")]
    reused = [item["fact_key"] for item in assessments if item.get("reusable")]
    reasons: list[str] = []
    for reason in REDISCOVERY_REASONS:
        if any(reason in item.get("rediscovery_reasons", []) for item in assessments):
            reasons.append(reason)
    return sanitize_for_persistence(
        {
            "protocol": "agentos.discovery-receipt/v1",
            "project_id": project_id,
            "performed": bool(rediscovered),
            "reused": reused,
            "rediscovered": rediscovered,
            "rediscovery_reasons": reasons,
            "assessments": assessments,
            "promoted": promoted or [],
            "created_at": _utc_now(),
        }
    )

"""Host-side Reuse Before Build gate backed by the Governance Directory."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from runtime_core.capability_resolution import (
    CapabilityCandidate,
    CapabilityResolution,
    resolve_capabilities,
)

from .governance_directory import REGISTRY_PATH, load_directory


_INACTIVE_STATES = {"retired", "superseded", "stale", "drifted"}
_STATE_PRIORITY = {
    "verified": 40,
    "observed": 30,
    "deployed": 30,
    "implemented": 20,
    "declared": 10,
}


def canonical_capability(value: str) -> str:
    capability = str(value or "").strip()
    if not capability:
        raise ValueError("capability is required")
    return capability if capability.startswith("capability://") else f"capability://{capability}"


def candidates_from_governance(path: Path = REGISTRY_PATH) -> list[CapabilityCandidate]:
    """Normalize active Governance Directory entities into portable candidates."""

    out: list[CapabilityCandidate] = []
    for entity in load_directory(path).get("entities", {}).values():
        state = str(entity.get("state") or "declared")
        if state in _INACTIVE_STATES:
            continue
        capabilities = {
            canonical_capability(item)
            for item in [*(entity.get("owns") or []), *(entity.get("provides") or [])]
            if str(item or "").strip()
        }
        if not capabilities:
            continue
        authority = entity.get("authority") or {}
        priority = _STATE_PRIORITY.get(state, 0)
        if authority.get("exclusive"):
            priority += 100
        out.append(
            CapabilityCandidate.from_values(
                str(entity.get("id") or ""),
                capabilities,
                priority=priority,
                metadata={
                    "state": state,
                    "kind": entity.get("kind"),
                    "owner": entity.get("owner"),
                    "implementation": entity.get("implementation") or {},
                    "authority": authority,
                },
            )
        )
    return out


def resolve_before_build(
    required_capabilities: Iterable[str],
    *,
    path: Path = REGISTRY_PATH,
    allow_build_when_missing: bool = False,
    force_build: bool = False,
    override_reason: str | None = None,
) -> CapabilityResolution:
    """Resolve a request against canonical governance before permitting a build.

    This is the host-side enforcement point. Callers should treat BUILD as the
    only decision that authorizes creation of a new implementation. REUSE and
    COMPOSE identify existing providers; DENY blocks the build request.
    """

    required = [canonical_capability(item) for item in required_capabilities]
    return resolve_capabilities(
        required,
        candidates_from_governance(path),
        allow_build_when_missing=allow_build_when_missing,
        force_build=force_build,
        override_reason=override_reason,
    )

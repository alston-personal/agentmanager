"""Pure capability resolution semantics for Reuse Before Build.

The resolver is intentionally host-neutral. Discovery, persistence, authorization,
and audit storage belong to the host; this module only makes a deterministic
resolution decision from a supplied candidate snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence


class ResolutionMode(str, Enum):
    REUSE = "reuse"
    COMPOSE = "compose"
    BUILD = "build"
    DENY = "deny"


@dataclass(frozen=True)
class CapabilityCandidate:
    """A normalized capability provider supplied by a host-side registry adapter."""

    candidate_id: str
    capabilities: frozenset[str]
    priority: int = 0
    available: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_values(
        cls,
        candidate_id: str,
        capabilities: Iterable[str],
        *,
        priority: int = 0,
        available: bool = True,
        metadata: Mapping[str, object] | None = None,
    ) -> "CapabilityCandidate":
        normalized_id = str(candidate_id).strip()
        if not normalized_id:
            raise ValueError("candidate_id is required")
        normalized = frozenset(str(item).strip() for item in capabilities if str(item).strip())
        if not normalized:
            raise ValueError("candidate capabilities are required")
        return cls(
            candidate_id=normalized_id,
            capabilities=normalized,
            priority=int(priority),
            available=bool(available),
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class CapabilityResolution:
    mode: ResolutionMode
    required_capabilities: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    reason: str
    override_reason: str | None = None

    @property
    def build_allowed(self) -> bool:
        return self.mode is ResolutionMode.BUILD


def _normalize_required(required_capabilities: Iterable[str]) -> tuple[str, ...]:
    normalized = sorted({str(item).strip() for item in required_capabilities if str(item).strip()})
    if not normalized:
        raise ValueError("at least one required capability is required")
    return tuple(normalized)


def resolve_capabilities(
    required_capabilities: Sequence[str],
    candidates: Iterable[CapabilityCandidate],
    *,
    allow_build_when_missing: bool = False,
    force_build: bool = False,
    override_reason: str | None = None,
) -> CapabilityResolution:
    """Resolve capabilities deterministically under a Reuse Before Build policy.

    Rules:
    1. Prefer one available candidate that satisfies the whole requirement.
    2. Otherwise compose available candidates if their union satisfies it.
    3. Build is allowed only when capability is still missing and the caller has
       explicitly enabled missing-capability builds.
    4. Forcing a build despite a reusable solution requires a non-empty override
       reason; otherwise the request is denied.

    Candidate ordering is deterministic: higher priority first, then candidate id.
    The host should persist the returned decision together with the registry
    snapshot/version that produced it when auditability is required.
    """

    required = _normalize_required(required_capabilities)
    required_set = set(required)
    usable = sorted(
        (item for item in candidates if item.available),
        key=lambda item: (-item.priority, item.candidate_id),
    )

    whole = [item for item in usable if required_set.issubset(item.capabilities)]
    selected: tuple[str, ...] = ()
    mode: ResolutionMode | None = None

    if whole:
        selected = (whole[0].candidate_id,)
        mode = ResolutionMode.REUSE
    else:
        uncovered = set(required_set)
        composed: list[str] = []
        remaining = list(usable)
        while uncovered:
            useful = [item for item in remaining if item.capabilities & uncovered]
            if not useful:
                break
            # Maximize newly covered capabilities first; preserve priority/id tie-break.
            useful.sort(
                key=lambda item: (
                    -len(item.capabilities & uncovered),
                    -item.priority,
                    item.candidate_id,
                )
            )
            chosen = useful[0]
            composed.append(chosen.candidate_id)
            uncovered -= chosen.capabilities
            remaining = [item for item in remaining if item.candidate_id != chosen.candidate_id]
        if not uncovered:
            selected = tuple(composed)
            mode = ResolutionMode.COMPOSE

    if mode is not None:
        if force_build:
            reason = (override_reason or "").strip()
            if not reason:
                return CapabilityResolution(
                    mode=ResolutionMode.DENY,
                    required_capabilities=required,
                    selected_candidate_ids=selected,
                    missing_capabilities=(),
                    reason="reusable capability exists; build override requires an explicit reason",
                )
            return CapabilityResolution(
                mode=ResolutionMode.BUILD,
                required_capabilities=required,
                selected_candidate_ids=selected,
                missing_capabilities=(),
                reason="explicit build override accepted despite reusable capability",
                override_reason=reason,
            )
        return CapabilityResolution(
            mode=mode,
            required_capabilities=required,
            selected_candidate_ids=selected,
            missing_capabilities=(),
            reason="existing capability satisfies request",
        )

    available_union: set[str] = set()
    for item in usable:
        available_union.update(item.capabilities)
    missing = tuple(sorted(required_set - available_union))

    if force_build or allow_build_when_missing:
        return CapabilityResolution(
            mode=ResolutionMode.BUILD,
            required_capabilities=required,
            selected_candidate_ids=(),
            missing_capabilities=missing,
            reason="no reusable capability satisfies request",
            override_reason=(override_reason or "").strip() or None,
        )

    return CapabilityResolution(
        mode=ResolutionMode.DENY,
        required_capabilities=required,
        selected_candidate_ids=(),
        missing_capabilities=missing,
        reason="capability missing and build authority was not granted",
    )

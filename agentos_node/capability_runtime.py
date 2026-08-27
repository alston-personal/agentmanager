"""AgentOS capability-level learning and consolidation primitives.

A capability is the lowest semantic owner of its own domain experience.
Libraries and executors do not need to know AgentOS exists; adapters turn
observable executions into CapabilityExperience records, reducers consolidate
those records into candidate capability state, and governance decides whether
a candidate may become canonical.

The runtime intentionally does NOT mutate canonical state automatically.
Promotion is explicit so capability learning cannot silently expand authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Iterable, Mapping, Protocol
import json


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}-{sha256(raw.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True)
class CapabilityExperience:
    """One observation owned by exactly one semantic capability."""

    capability_id: str
    node_id: str
    observation: Mapping[str, Any]
    outcome: Mapping[str, Any]
    policy_used: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    schema: str = "agentos.capability-experience/v1"
    experience_id: str = ""

    def __post_init__(self) -> None:
        if not self.capability_id:
            raise ValueError("capability_id is required")
        if not self.node_id:
            raise ValueError("node_id is required")
        if not self.experience_id:
            payload = {
                "capability_id": self.capability_id,
                "node_id": self.node_id,
                "observation": self.observation,
                "outcome": self.outcome,
                "policy_used": self.policy_used,
                "provenance": self.provenance,
                "created_at": self.created_at,
            }
            object.__setattr__(self, "experience_id", _stable_id("exp", payload))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityState:
    """Candidate or canonical state for one capability."""

    capability_id: str
    version: int
    payload: Mapping[str, Any]
    support: int
    confidence: float
    state_kind: str = "candidate"
    evidence_ids: tuple[str, ...] = ()
    parent_state_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    schema: str = "agentos.capability-state/v1"
    state_id: str = ""

    def __post_init__(self) -> None:
        if self.state_kind not in {"candidate", "canonical", "shadow", "retired"}:
            raise ValueError(f"invalid state_kind: {self.state_kind}")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if self.support < 0:
            raise ValueError("support must be >= 0")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.state_id:
            payload = {
                "capability_id": self.capability_id,
                "version": self.version,
                "payload": self.payload,
                "support": self.support,
                "confidence": self.confidence,
                "state_kind": self.state_kind,
                "evidence_ids": self.evidence_ids,
                "parent_state_id": self.parent_state_id,
            }
            object.__setattr__(self, "state_id", _stable_id("capstate", payload))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapabilityReducer(Protocol):
    """Domain-owned reducer: Experience[] -> candidate CapabilityState."""

    def __call__(
        self,
        capability_id: str,
        experiences: list[CapabilityExperience],
        current: CapabilityState | None,
    ) -> CapabilityState:
        ...


class CapabilityEvaluator(Protocol):
    """Returns whether a candidate is safe/valuable enough to be promotable."""

    def __call__(
        self,
        candidate: CapabilityState,
        current: CapabilityState | None,
    ) -> tuple[bool, Mapping[str, Any]]:
        ...


@dataclass
class ConsolidationResult:
    candidate: CapabilityState
    promotable: bool
    evaluation: Mapping[str, Any]


class CapabilityRuntime:
    """Generic capability learning boundary.

    The runtime owns protocol mechanics only. Domain intelligence lives in the
    reducer/evaluator supplied by the capability. `consolidate` never promotes
    automatically; callers/governance must call `promote` explicitly.
    """

    def __init__(self) -> None:
        self._experiences: dict[str, dict[str, CapabilityExperience]] = {}
        self._canonical: dict[str, CapabilityState] = {}
        self._candidates: dict[str, CapabilityState] = {}

    def observe(self, experience: CapabilityExperience) -> str:
        bucket = self._experiences.setdefault(experience.capability_id, {})
        bucket.setdefault(experience.experience_id, experience)
        return experience.experience_id

    def experiences(self, capability_id: str) -> list[CapabilityExperience]:
        return list(self._experiences.get(capability_id, {}).values())

    def canonical(self, capability_id: str) -> CapabilityState | None:
        return self._canonical.get(capability_id)

    def candidate(self, capability_id: str) -> CapabilityState | None:
        return self._candidates.get(capability_id)

    def consolidate(
        self,
        capability_id: str,
        reducer: CapabilityReducer,
        evaluator: CapabilityEvaluator,
    ) -> ConsolidationResult:
        xs = self.experiences(capability_id)
        if not xs:
            raise ValueError(f"no experiences for capability {capability_id}")
        current = self.canonical(capability_id)
        candidate = reducer(capability_id, xs, current)
        if candidate.capability_id != capability_id:
            raise ValueError("reducer returned state for a different capability")
        if candidate.state_kind != "candidate":
            raise ValueError("reducer must return candidate state")
        self._candidates[capability_id] = candidate
        promotable, evidence = evaluator(candidate, current)
        return ConsolidationResult(candidate, bool(promotable), dict(evidence))

    def promote(
        self,
        capability_id: str,
        *,
        approved: bool,
        authority_receipt: Mapping[str, Any],
    ) -> CapabilityState:
        """Explicit governance gate from candidate -> canonical.

        `approved=True` is insufficient by itself: a non-empty authority receipt
        is required so promotion always has provenance.
        """
        if not approved:
            raise PermissionError("candidate promotion was not approved")
        if not authority_receipt:
            raise PermissionError("authority receipt is required")
        candidate = self._candidates.get(capability_id)
        if candidate is None:
            raise ValueError(f"no candidate for capability {capability_id}")
        canonical = CapabilityState(
            capability_id=candidate.capability_id,
            version=candidate.version,
            payload=dict(candidate.payload),
            support=candidate.support,
            confidence=candidate.confidence,
            state_kind="canonical",
            evidence_ids=candidate.evidence_ids,
            parent_state_id=candidate.parent_state_id,
        )
        self._canonical[capability_id] = canonical
        return canonical


def weighted_numeric_profile_reducer(
    parameter_names: Iterable[str],
    *,
    quality_key: str = "quality",
) -> CapabilityReducer:
    """Small reference reducer for numeric policy parameters.

    Each experience's `policy_used` contributes values. Outcome quality is a
    weight in [0, 1]. This is deliberately generic; domain capabilities can
    replace it with clustering, regime detection, Bayesian updates, etc.
    """
    names = tuple(parameter_names)

    def reduce(
        capability_id: str,
        experiences: list[CapabilityExperience],
        current: CapabilityState | None,
    ) -> CapabilityState:
        totals = {name: 0.0 for name in names}
        weights = {name: 0.0 for name in names}
        usable = 0
        for exp in experiences:
            quality = max(0.0, min(1.0, float(exp.outcome.get(quality_key, 1.0))))
            for name in names:
                if name not in exp.policy_used:
                    continue
                try:
                    value = float(exp.policy_used[name])
                except (TypeError, ValueError):
                    continue
                w = max(quality, 1e-6)
                totals[name] += value * w
                weights[name] += w
                usable += 1
        policy = {
            name: totals[name] / weights[name]
            for name in names
            if weights[name] > 0
        }
        if not policy:
            raise ValueError("experiences contain no usable numeric parameters")
        version = 1 if current is None else current.version + 1
        confidence = min(0.99, len(experiences) / 20.0)
        return CapabilityState(
            capability_id=capability_id,
            version=version,
            payload={"policy": policy},
            support=len(experiences),
            confidence=confidence,
            state_kind="candidate",
            evidence_ids=tuple(exp.experience_id for exp in experiences),
            parent_state_id=current.state_id if current else None,
        )

    return reduce


def non_regression_evaluator(
    candidate: CapabilityState,
    current: CapabilityState | None,
) -> tuple[bool, Mapping[str, Any]]:
    """Conservative reference evaluator.

    First state needs at least two observations. Later candidates may not have
    lower confidence than the current canonical state. Real capabilities should
    additionally run domain benchmarks/shadow evaluation before promotion.
    """
    if current is None:
        ok = candidate.support >= 2
        return ok, {"reason": "bootstrap_support", "support": candidate.support}
    ok = candidate.confidence >= current.confidence
    return ok, {
        "reason": "confidence_non_regression",
        "candidate_confidence": candidate.confidence,
        "current_confidence": current.confidence,
    }

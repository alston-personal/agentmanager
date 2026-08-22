"""Adaptive, reversible memory lifecycle for the Cognitive Kernel.

Forgetting is modeled as attention decay, not destructive deletion. Knowledge
content and provenance remain immutable; this module tracks how likely a memory
is to participate in ordinary retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import IntEnum
import math
from typing import Iterable


class MemoryTier(IntEnum):
    """Retrieval tiers ordered from least to most cognitively active."""

    ARCHIVE = 0
    COLD = 1
    COOL = 2
    WARM = 3
    HOT = 4


_TIER_RETRIEVAL_WEIGHT = {
    MemoryTier.ARCHIVE: 0.03,
    MemoryTier.COLD: 0.20,
    MemoryTier.COOL: 0.45,
    MemoryTier.WARM: 0.75,
    MemoryTier.HOT: 1.00,
}


@dataclass(frozen=True)
class MemoryLifecycleState:
    knowledge_id: str
    tier: MemoryTier = MemoryTier.WARM
    activation: float = 0.65
    access_count: int = 0
    last_accessed_at: datetime | None = None
    last_evaluated_at: datetime | None = None
    pinned: bool = False
    dependency_count: int = 0
    historical_value: float = 0.0
    superseded: bool = False

    def __post_init__(self) -> None:
        if not self.knowledge_id.strip():
            raise ValueError("knowledge_id is required")
        if not 0.0 <= self.activation <= 1.0:
            raise ValueError("activation must be between 0 and 1")
        if self.access_count < 0 or self.dependency_count < 0:
            raise ValueError("counts cannot be negative")
        if not 0.0 <= self.historical_value <= 1.0:
            raise ValueError("historical_value must be between 0 and 1")

    @property
    def retrieval_weight(self) -> float:
        """Attention multiplier used by retrieval engines."""
        tier_weight = _TIER_RETRIEVAL_WEIGHT[self.tier]
        return round(tier_weight * (0.35 + 0.65 * self.activation), 6)


@dataclass(frozen=True)
class MemoryLifecyclePolicy:
    """Deterministic reference policy; storage/scheduling remain replaceable."""

    decay_half_life_days: float = 45.0
    access_boost: float = 0.18
    strong_relevance_boost: float = 0.30
    dependency_floor: float = 0.35
    historical_floor: float = 0.25

    def __post_init__(self) -> None:
        if self.decay_half_life_days <= 0:
            raise ValueError("decay_half_life_days must be positive")

    @staticmethod
    def _ensure_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def decay(self, state: MemoryLifecycleState, *, now: datetime) -> MemoryLifecycleState:
        """Apply time decay without deleting or severing provenance.

        Supersession lowers ordinary attention, but dependency/history floors are
        applied afterwards so required lineage cannot be pushed below its
        reconstruction floor merely because a newer belief exists.
        """
        now = self._ensure_aware(now)
        anchor = state.last_evaluated_at or state.last_accessed_at
        if anchor is None:
            return replace(state, last_evaluated_at=now)
        anchor = self._ensure_aware(anchor)
        elapsed_days = max(0.0, (now - anchor).total_seconds() / 86400.0)
        factor = math.pow(0.5, elapsed_days / self.decay_half_life_days)
        activation = state.activation * factor

        # Superseded memories should gracefully leave active cognition, but this
        # penalty must not erase floors needed by downstream dependencies/history.
        if state.superseded and not state.pinned:
            activation *= 0.65

        if state.dependency_count:
            activation = max(activation, self.dependency_floor)
        if state.historical_value:
            activation = max(
                activation,
                self.historical_floor * state.historical_value,
            )
        if state.pinned:
            activation = max(activation, 0.75)

        activation = max(0.0, min(1.0, activation))
        return replace(
            state,
            activation=activation,
            tier=self.tier_for_activation(activation, state=state),
            last_evaluated_at=now,
        )

    def reinforce(
        self,
        state: MemoryLifecycleState,
        *,
        now: datetime,
        relevance: float = 0.0,
        explicit_recall: bool = False,
    ) -> MemoryLifecycleState:
        """Reactivate a memory when it becomes useful again."""
        if not 0.0 <= relevance <= 1.0:
            raise ValueError("relevance must be between 0 and 1")
        now = self._ensure_aware(now)
        state = self.decay(state, now=now)
        boost = self.access_boost + self.strong_relevance_boost * relevance
        if explicit_recall:
            boost += 0.25
        activation = min(1.0, state.activation + boost)
        return replace(
            state,
            activation=activation,
            tier=self.tier_for_activation(activation, state=state),
            access_count=state.access_count + 1,
            last_accessed_at=now,
            last_evaluated_at=now,
        )

    @staticmethod
    def tier_for_activation(
        activation: float,
        *,
        state: MemoryLifecycleState | None = None,
    ) -> MemoryTier:
        if state and state.pinned:
            return MemoryTier.HOT
        if activation >= 0.78:
            return MemoryTier.HOT
        if activation >= 0.55:
            return MemoryTier.WARM
        if activation >= 0.32:
            return MemoryTier.COOL
        if activation >= 0.12:
            return MemoryTier.COLD
        return MemoryTier.ARCHIVE


class InMemoryLifecycleStore:
    """Small deterministic reference store; production persistence is pluggable."""

    def __init__(self) -> None:
        self._states: dict[str, MemoryLifecycleState] = {}

    def upsert(self, states: Iterable[MemoryLifecycleState]) -> None:
        for state in states:
            self._states[state.knowledge_id] = state

    def get(self, knowledge_id: str) -> MemoryLifecycleState | None:
        return self._states.get(knowledge_id)

    def state_for(self, knowledge_id: str) -> MemoryLifecycleState:
        return self._states.get(knowledge_id) or MemoryLifecycleState(knowledge_id=knowledge_id)

    def records(self) -> tuple[MemoryLifecycleState, ...]:
        return tuple(self._states[key] for key in sorted(self._states))

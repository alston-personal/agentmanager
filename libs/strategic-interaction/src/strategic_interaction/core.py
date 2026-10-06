from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{sha256(raw.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True)
class Participant:
    participant_id: str
    role: str
    observable_state: Mapping[str, Any] = field(default_factory=dict)
    private_state_known: Mapping[str, Any] = field(default_factory=dict)
    schema: str = "agentos.strategic-participant/v1"

    def __post_init__(self) -> None:
        if not self.participant_id.strip():
            raise ValueError("participant_id is required")
        if not self.role.strip():
            raise ValueError("role is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Belief:
    observer_id: str
    subject_id: str
    hypothesis: str
    probability: float
    evidence_refs: tuple[str, ...] = ()
    schema: str = "agentos.strategic-belief/v1"

    def __post_init__(self) -> None:
        if not 0 <= float(self.probability) <= 1:
            raise ValueError("probability must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Incentive:
    participant_id: str
    objective: str
    weight: float = 1.0
    constraints: Mapping[str, Any] = field(default_factory=dict)
    schema: str = "agentos.strategic-incentive/v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionEvent:
    sequence: int
    actor_id: str
    action_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    observed_at: str | None = None
    schema: str = "agentos.strategic-action/v1"

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if not self.actor_id.strip():
            raise ValueError("actor_id is required")
        if not self.action_type.strip():
            raise ValueError("action_type is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InteractionState:
    interaction_type: str
    observed_at: str
    participants: tuple[Participant, ...]
    environment: Mapping[str, Any] = field(default_factory=dict)
    beliefs: tuple[Belief, ...] = ()
    incentives: tuple[Incentive, ...] = ()
    history: tuple[ActionEvent, ...] = ()
    source_refs: tuple[str, ...] = ()
    schema: str = "agentos.strategic-interaction-state/v1"
    interaction_id: str = ""

    def __post_init__(self) -> None:
        if not self.interaction_type.strip():
            raise ValueError("interaction_type is required")
        ids = [item.participant_id for item in self.participants]
        if len(ids) != len(set(ids)):
            raise ValueError("participant IDs must be unique")
        history = list(self.history)
        if history != sorted(history, key=lambda item: item.sequence):
            raise ValueError("history must be ordered by sequence")
        if not self.interaction_id:
            payload = {
                "interaction_type": self.interaction_type,
                "observed_at": self.observed_at,
                "participants": [p.to_dict() for p in self.participants],
                "environment": dict(self.environment),
                "beliefs": [b.to_dict() for b in self.beliefs],
                "incentives": [i.to_dict() for i in self.incentives],
                "history": [a.to_dict() for a in self.history],
                "source_refs": list(self.source_refs),
            }
            object.__setattr__(self, "interaction_id", _stable_id("interaction", payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "interaction_id": self.interaction_id,
            "interaction_type": self.interaction_type,
            "observed_at": self.observed_at,
            "participants": [p.to_dict() for p in self.participants],
            "environment": dict(self.environment),
            "beliefs": [b.to_dict() for b in self.beliefs],
            "incentives": [i.to_dict() for i in self.incentives],
            "history": [a.to_dict() for a in self.history],
            "source_refs": list(self.source_refs),
        }

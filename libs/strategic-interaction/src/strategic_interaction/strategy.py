from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import copy
import json
from typing import Any, Mapping


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()[:20]


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise ValueError("delta path must not be empty")
    cursor = target
    for part in parts[:-1]:
        current = cursor.setdefault(part, {})
        if not isinstance(current, dict):
            raise ValueError(f"cannot descend through non-object path: {path}")
        cursor = current
    cursor[parts[-1]] = copy.deepcopy(value)


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    parameters: Mapping[str, Any]
    tags: tuple[str, ...] = ()
    schema: str = "agentos.strategic-strategy/v1"

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyDelta:
    delta_id: str
    base_ref: str
    set_values: Mapping[str, Any] = field(default_factory=dict)
    add_values: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    strategy_id: str | None = None
    rationale: str = ""
    schema: str = "agentos.strategic-strategy-delta/v1"

    def __post_init__(self) -> None:
        if not self.delta_id.strip():
            raise ValueError("delta_id is required")
        if not self.base_ref.strip():
            raise ValueError("base_ref is required")


@dataclass(frozen=True)
class ResolvedStrategy:
    strategy_id: str
    base_id: str
    delta_id: str
    parameters: Mapping[str, Any]
    fingerprint: str
    schema: str = "agentos.strategic-resolved-strategy/v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_strategy(base: StrategySpec, delta: StrategyDelta) -> ResolvedStrategy:
    if delta.base_ref != base.strategy_id:
        raise ValueError("delta base_ref does not match base strategy")

    resolved = copy.deepcopy(dict(base.parameters))
    for path, value in delta.set_values.items():
        _set_path(resolved, str(path), value)

    for path, values in delta.add_values.items():
        parts = str(path).split(".")
        cursor = resolved
        for part in parts[:-1]:
            current = cursor.setdefault(part, {})
            if not isinstance(current, dict):
                raise ValueError(f"cannot descend through non-object add path: {path}")
            cursor = current
        leaf = parts[-1]
        existing = cursor.setdefault(leaf, [])
        if not isinstance(existing, list):
            raise ValueError(f"add target must be list: {path}")
        for value in values:
            if value not in existing:
                existing.append(copy.deepcopy(value))

    strategy_id = delta.strategy_id or delta.delta_id
    payload = {
        "strategy_id": strategy_id,
        "base_id": base.strategy_id,
        "delta_id": delta.delta_id,
        "parameters": resolved,
    }
    return ResolvedStrategy(
        strategy_id=strategy_id,
        base_id=base.strategy_id,
        delta_id=delta.delta_id,
        parameters=resolved,
        fingerprint=_fingerprint(payload),
    )

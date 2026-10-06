from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise ValueError("delta path must not be empty")
    cursor = target
    for part in parts[:-1]:
        current = cursor.get(part)
        if current is None:
            current = {}
            cursor[part] = current
        if not isinstance(current, dict):
            raise ValueError(f"cannot descend into non-object path: {path}")
        cursor = current
    cursor[parts[-1]] = copy.deepcopy(value)


@dataclass(frozen=True)
class StrategyInstance:
    strategy_id: str
    base_id: str
    delta_id: str
    resolved: Mapping[str, Any]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "agentos.market-strategy-instance/v1",
            "strategy_id": self.strategy_id,
            "base_id": self.base_id,
            "delta_id": self.delta_id,
            "fingerprint": self.fingerprint,
            "resolved": copy.deepcopy(dict(self.resolved)),
        }


def resolve_strategy(base: Mapping[str, Any], delta: Mapping[str, Any]) -> StrategyInstance:
    base_id = str(base.get("strategy_id") or "").strip()
    delta_id = str(delta.get("delta_id") or "").strip()
    if not base_id:
        raise ValueError("base strategy_id is required")
    if not delta_id:
        raise ValueError("delta delta_id is required")
    if str(delta.get("base_ref") or "") != base_id:
        raise ValueError("delta base_ref does not match base strategy_id")

    resolved = copy.deepcopy(dict(base))
    for path, value in dict(delta.get("set") or {}).items():
        _set_path(resolved, str(path), value)

    additions = dict(delta.get("add") or {})
    for path, values in additions.items():
        parts = str(path).split(".")
        cursor = resolved
        for part in parts[:-1]:
            current = cursor.setdefault(part, {})
            if not isinstance(current, dict):
                raise ValueError(f"cannot descend into non-object add path: {path}")
            cursor = current
        leaf = parts[-1]
        existing = cursor.setdefault(leaf, [])
        if not isinstance(existing, list):
            raise ValueError(f"add target must be a list: {path}")
        for value in list(values):
            if value not in existing:
                existing.append(copy.deepcopy(value))

    strategy_id = str(delta.get("strategy_id") or delta_id)
    resolved["strategy_id"] = strategy_id
    resolved["derived_from"] = {"base": base_id, "delta": delta_id}
    fingerprint = _stable_hash(resolved)
    return StrategyInstance(
        strategy_id=strategy_id,
        base_id=base_id,
        delta_id=delta_id,
        resolved=resolved,
        fingerprint=fingerprint,
    )

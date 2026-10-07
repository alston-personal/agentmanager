from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ReconciliationSource:
    name: str
    ir: Mapping[str, Any]
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("source name must be non-empty")
        if self.weight < 0:
            raise ValueError("source weight must be >= 0")


@dataclass(frozen=True)
class ReconciliationPolicy:
    per_field: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    preserve_from: Mapping[str, str] = field(default_factory=dict)

    def weight_for(self, field_path: str, source: ReconciliationSource) -> float:
        override = self.per_field.get(field_path, {}).get(source.name)
        value = source.weight if override is None else override
        if value < 0:
            raise ValueError(f"weight for source={source.name!r}, field={field_path!r} must be >= 0")
        return float(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _choose_scalar(field_path, candidates, policy):
    pinned = policy.preserve_from.get(field_path)
    if pinned:
        for source, value in candidates:
            if source.name == pinned:
                return value

    if all(_is_number(value) for _, value in candidates):
        weights = [policy.weight_for(field_path, source) for source, _ in candidates]
        denominator = sum(weights)
        if denominator > 0:
            return sum(float(value) * weight for (_, value), weight in zip(candidates, weights)) / denominator

    return max(candidates, key=lambda item: policy.weight_for(field_path, item[0]))[1]


def _merge_node(nodes, policy, path=""):
    keys = set()
    for _, node in nodes:
        keys.update(node.keys())

    out = {}
    for key in sorted(keys):
        field_path = f"{path}.{key}" if path else key
        candidates = [(source, node[key]) for source, node in nodes if key in node]
        mappings = [(source, value) for source, value in candidates if isinstance(value, Mapping)]
        scalars = [(source, value) for source, value in candidates if not isinstance(value, Mapping)]

        if mappings and scalars:
            pinned = policy.preserve_from.get(field_path)
            if pinned:
                selected = next(((source, value) for source, value in candidates if source.name == pinned), None)
                if selected is not None:
                    out[key] = selected[1]
                    continue
            out[key] = max(candidates, key=lambda item: policy.weight_for(field_path, item[0]))[1]
        elif mappings:
            out[key] = _merge_node(mappings, policy, field_path)
        else:
            out[key] = _choose_scalar(field_path, scalars, policy)
    return out


def weighted_reconcile_ir(sources: Sequence[ReconciliationSource], policy: ReconciliationPolicy | None = None) -> dict[str, Any]:
    """Fuse compatible Character IR sources while retaining the existing IR schema."""
    if not sources:
        raise ValueError("at least one reconciliation source is required")

    policy = policy or ReconciliationPolicy()
    schemas = {source.ir.get("schema") for source in sources if source.ir.get("schema") is not None}
    if len(schemas) > 1:
        raise ValueError(f"weighted reconciliation requires compatible Character IR schemas; got {sorted(schemas)!r}")

    merged = _merge_node([(source, source.ir) for source in sources], policy)
    merged["reconciliation"] = {
        "kind": "weighted-multi-source",
        "sources": [{"name": source.name, "weight": source.weight} for source in sources],
        "per_field": {path: dict(weights) for path, weights in policy.per_field.items()},
        "preserve_from": dict(policy.preserve_from),
        "policy": "reuse the existing Character IR schema; stronger source evidence wins conflicts unless field policy overrides it",
    }
    return merged

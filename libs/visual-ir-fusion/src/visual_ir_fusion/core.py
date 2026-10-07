from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Mapping, Sequence


_STATUS_RANK = {
    "observed": 3,
    "inferred": 2,
    "unresolved": 1,
}


@dataclass(frozen=True)
class IRSource:
    name: str
    ir: Mapping[str, Any]
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("IRSource.name must be non-empty")
        if self.weight < 0:
            raise ValueError("IRSource.weight must be >= 0")


@dataclass(frozen=True)
class FusionPolicy:
    per_dimension: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    protected_dimensions: Sequence[str] = ()
    minimum_preservation: Mapping[str, float] = field(default_factory=dict)

    def weight_for(self, dimension: str, source: IRSource) -> float:
        override = self.per_dimension.get(dimension, {}).get(source.name)
        weight = source.weight if override is None else override
        if weight < 0:
            raise ValueError(
                f"Weight for source={source.name!r}, dimension={dimension!r} must be >= 0"
            )
        return float(weight)


def _is_leaf(value: Any) -> bool:
    return isinstance(value, Mapping) and "value" in value


def _leaf_confidence(leaf: Mapping[str, Any]) -> float:
    value = leaf.get("confidence", 1.0)
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid confidence: {value!r}") from exc
    return max(0.0, min(1.0, value))


def _effective_weight(
    dimension: str,
    source: IRSource,
    leaf: Mapping[str, Any],
    policy: FusionPolicy,
) -> float:
    return policy.weight_for(dimension, source) * _leaf_confidence(leaf)


def _fuse_leaf(
    dimension: str,
    candidates: list[tuple[IRSource, Mapping[str, Any]]],
    policy: FusionPolicy,
) -> dict[str, Any]:
    usable = [
        (source, leaf, _effective_weight(dimension, source, leaf, policy))
        for source, leaf in candidates
        if leaf.get("status", "inferred") != "unresolved"
        and leaf.get("value") is not None
    ]

    if not usable:
        return {
            "value": None,
            "confidence": 0.0,
            "status": "unresolved",
            "provenance": [
                {
                    "source": source.name,
                    "status": leaf.get("status", "unresolved"),
                    "value": leaf.get("value"),
                }
                for source, leaf in candidates
            ],
        }

    values = [leaf["value"] for _, leaf, _ in usable]
    numeric = all(
        isinstance(value, Real) and not isinstance(value, bool) for value in values
    )

    if numeric:
        denominator = sum(weight for _, _, weight in usable)
        if denominator <= 0:
            winner_source, winner_leaf, winner_weight = usable[0]
            fused_value = winner_leaf["value"]
        else:
            fused_value = sum(
                float(leaf["value"]) * weight for _, leaf, weight in usable
            ) / denominator
            winner_source, winner_leaf, winner_weight = max(
                usable, key=lambda item: item[2]
            )
    else:
        winner_source, winner_leaf, winner_weight = max(
            usable,
            key=lambda item: (
                item[2],
                _STATUS_RANK.get(item[1].get("status", "inferred"), 0),
            ),
        )
        fused_value = winner_leaf["value"]

    total_weight = sum(weight for _, _, weight in usable)
    confidence = 0.0 if total_weight <= 0 else winner_weight / total_weight
    confidence = max(confidence, _leaf_confidence(winner_leaf) * 0.5)

    return {
        "value": fused_value,
        "confidence": round(min(1.0, confidence), 6),
        "status": winner_leaf.get("status", "inferred"),
        "provenance": [
            {
                "source": source.name,
                "source_weight": policy.weight_for(dimension, source),
                "confidence": _leaf_confidence(leaf),
                "effective_weight": round(weight, 6),
                "status": leaf.get("status", "inferred"),
                "value": leaf.get("value"),
            }
            for source, leaf, weight in usable
        ],
    }


def _fuse_node(
    path: str,
    nodes: list[tuple[IRSource, Mapping[str, Any]]],
    policy: FusionPolicy,
) -> dict[str, Any]:
    keys: set[str] = set()
    for _, node in nodes:
        keys.update(node.keys())

    result: dict[str, Any] = {}
    for key in sorted(keys):
        child_path = f"{path}.{key}" if path else key
        candidates = [
            (source, node[key])
            for source, node in nodes
            if key in node
        ]
        if not candidates:
            continue

        leaf_candidates = [
            (source, value)
            for source, value in candidates
            if _is_leaf(value)
        ]
        nested_candidates = [
            (source, value)
            for source, value in candidates
            if isinstance(value, Mapping) and not _is_leaf(value)
        ]

        if leaf_candidates and not nested_candidates:
            result[key] = _fuse_leaf(child_path, leaf_candidates, policy)
        elif nested_candidates and not leaf_candidates:
            result[key] = _fuse_node(child_path, nested_candidates, policy)
        else:
            raise ValueError(
                f"Incompatible IR shapes at {child_path!r}: leaf and nested values mixed"
            )

    return result


def fuse_ir(
    sources: Sequence[IRSource],
    policy: FusionPolicy | None = None,
) -> dict[str, Any]:
    if not sources:
        raise ValueError("At least one IRSource is required")

    policy = policy or FusionPolicy()
    nodes: list[tuple[IRSource, Mapping[str, Any]]] = []

    for source in sources:
        schema = source.ir.get("schema")
        if schema not in (None, "visual-ir/v0.1"):
            raise ValueError(
                f"Unsupported IR schema from {source.name!r}: {schema!r}"
            )
        dimensions = source.ir.get("dimensions")
        if not isinstance(dimensions, Mapping):
            raise ValueError(
                f"IR source {source.name!r} must contain a mapping at 'dimensions'"
            )
        nodes.append((source, dimensions))

    return {
        "schema": "visual-ir/v0.1",
        "kind": "fused",
        "sources": [
            {"name": source.name, "weight": source.weight}
            for source in sources
        ],
        "dimensions": _fuse_node("", nodes, policy),
    }


def _similarity(expected: Any, actual: Any) -> float:
    if expected is None or actual is None:
        return 0.0
    if (
        isinstance(expected, Real)
        and not isinstance(expected, bool)
        and isinstance(actual, Real)
        and not isinstance(actual, bool)
    ):
        denominator = max(abs(float(expected)), abs(float(actual)), 1.0)
        return max(0.0, 1.0 - abs(float(expected) - float(actual)) / denominator)
    if isinstance(expected, list) and isinstance(actual, list):
        if not expected and not actual:
            return 1.0
        union = set(map(str, expected)) | set(map(str, actual))
        if not union:
            return 1.0
        intersection = set(map(str, expected)) & set(map(str, actual))
        return len(intersection) / len(union)
    return 1.0 if expected == actual else 0.0


def _collect_leaves(
    node: Mapping[str, Any],
    path: str = "",
) -> dict[str, Mapping[str, Any]]:
    leaves: dict[str, Mapping[str, Any]] = {}
    for key, value in node.items():
        child_path = f"{path}.{key}" if path else key
        if _is_leaf(value):
            leaves[child_path] = value
        elif isinstance(value, Mapping):
            leaves.update(_collect_leaves(value, child_path))
    return leaves


def score_preservation(
    target_ir: Mapping[str, Any],
    actual_ir: Mapping[str, Any],
    *,
    dimensions: Sequence[str] | None = None,
) -> dict[str, Any]:
    target = _collect_leaves(target_ir.get("dimensions", {}))
    actual = _collect_leaves(actual_ir.get("dimensions", {}))

    selected = list(dimensions) if dimensions is not None else sorted(target)
    scores: dict[str, float] = {}

    for dimension in selected:
        target_leaf = target.get(dimension)
        actual_leaf = actual.get(dimension)
        if not target_leaf or not actual_leaf:
            scores[dimension] = 0.0
            continue
        scores[dimension] = round(
            _similarity(target_leaf.get("value"), actual_leaf.get("value")),
            6,
        )

    overall = sum(scores.values()) / len(scores) if scores else 1.0
    return {
        "schema": "visual-ir-preservation/v0.1",
        "overall": round(overall, 6),
        "dimensions": scores,
    }

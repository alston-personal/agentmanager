"""Compile deterministic observation values from governed Experience IR.

This is an execution/benchmark adapter, not an authority store. The canonical
learned artifact remains Experience IR. Only explicit IR `set` nodes whose
predicates are declared in `expected_behavior_dimensions` are projected.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


OBSERVATION_SCHEMA = "agentos.experience-observation-projection/v1"


class ExperienceObservationError(ValueError):
    pass


def _typed_value(value: Mapping[str, Any]) -> Any:
    if not isinstance(value, Mapping) or "type" not in value or "value" not in value:
        raise ExperienceObservationError("IR set node requires a typed value")
    value_type = value.get("type")
    raw = value.get("value")
    if value_type in {"symbol", "string"}:
        if not isinstance(raw, str):
            raise ExperienceObservationError("string/symbol observation must be a string")
        return raw
    if value_type == "boolean":
        if not isinstance(raw, bool):
            raise ExperienceObservationError("boolean observation must be boolean")
        return raw
    if value_type == "number":
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ExperienceObservationError("number observation must be numeric")
        return raw
    if value_type == "null":
        if raw is not None:
            raise ExperienceObservationError("null observation must be null")
        return None
    if value_type == "list":
        if not isinstance(raw, list):
            raise ExperienceObservationError("list observation must be a list")
        return raw
    if value_type == "object":
        if not isinstance(raw, Mapping):
            raise ExperienceObservationError("object observation must be an object")
        return dict(raw)
    raise ExperienceObservationError(f"unsupported typed observation: {value_type}")


def compile_experience_observations(
    hydration: Mapping[str, Any],
    *,
    allowed_dimensions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compile explicit observation values from hydrated Experience IR.

    Conflicting values fail closed. Missing dimensions are reported rather than
    guessed. This makes the weak-executor context deterministic without turning
    display summaries or ad-hoc payloads back into the learned representation.
    """
    if not isinstance(hydration, Mapping):
        raise ExperienceObservationError("hydration must be an object")
    items = hydration.get("items")
    if not isinstance(items, list):
        raise ExperienceObservationError("hydration.items must be a list")

    allowed = set(allowed_dimensions) if allowed_dimensions is not None else None
    values: dict[str, Any] = {}
    sources: dict[str, list[str]] = {}

    for item in items:
        if not isinstance(item, Mapping):
            raise ExperienceObservationError("hydration item must be an object")
        experience_id = item.get("experience_id")
        if not isinstance(experience_id, str) or not experience_id:
            raise ExperienceObservationError("hydration item experience_id is required")
        dimensions = item.get("expected_behavior_dimensions")
        ir = item.get("ir")
        if not isinstance(dimensions, list) or any(not isinstance(d, str) or not d for d in dimensions):
            raise ExperienceObservationError("expected_behavior_dimensions must be a list of strings")
        if not isinstance(ir, Mapping) or not isinstance(ir.get("nodes"), list):
            raise ExperienceObservationError("hydration item IR nodes are required")
        expected = set(dimensions)
        for node in ir["nodes"]:
            if not isinstance(node, Mapping) or node.get("op") != "set":
                continue
            predicate = node.get("predicate")
            if not isinstance(predicate, str) or predicate not in expected:
                continue
            if allowed is not None and predicate not in allowed:
                continue
            value = _typed_value(node.get("value"))
            if predicate in values and values[predicate] != value:
                raise ExperienceObservationError(
                    f"conflicting Experience IR observation for {predicate}"
                )
            values[predicate] = value
            sources.setdefault(predicate, []).append(experience_id)

    requested = list(allowed_dimensions or ())
    missing = [dimension for dimension in requested if dimension not in values]
    return {
        "schema": OBSERVATION_SCHEMA,
        "project_id": hydration.get("project_id"),
        "hydration_digest": hydration.get("digest"),
        "values": values,
        "sources": sources,
        "missing_dimensions": missing,
        "derived_from_experience_ir": True,
        "credential_exposed": False,
    }

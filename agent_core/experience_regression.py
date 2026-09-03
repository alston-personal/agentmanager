"""Machine-readable before/after and bounded Experience attribution reports."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


DELTA_SCHEMA = "agentos.experience-behavior-delta/v1"
ATTRIBUTION_SCHEMA = "agentos.experience-attribution/v1"

VALID_DELTAS = {"improved", "unchanged-correct", "unchanged-wrong", "regressed"}
VALID_ATTRIBUTION = {"direct", "supported", "ambiguous", "no-observed-effect", "negative"}


def _normalize_dimensions(value: Mapping[str, Any], *, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    out: dict[str, dict[str, Any]] = {}
    for dimension, result in value.items():
        if not isinstance(dimension, str) or not dimension:
            raise ValueError(f"{label} dimension names must be non-empty strings")
        if not isinstance(result, Mapping) or not isinstance(result.get("pass"), bool):
            raise ValueError(f"{label}.{dimension} requires boolean pass")
        out[dimension] = {
            "value": result.get("value"),
            "pass": result["pass"],
        }
    return out


def _candidate_map(hydration: Mapping[str, Any]) -> dict[str, list[str]]:
    items = hydration.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ValueError("hydration.items must be a list")
    out: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("hydration item must be an object")
        experience_id = item.get("experience_id")
        dimensions = item.get("expected_behavior_dimensions")
        if not isinstance(experience_id, str) or not experience_id:
            raise ValueError("hydration item experience_id is required")
        if not isinstance(dimensions, list) or any(not isinstance(d, str) or not d for d in dimensions):
            raise ValueError("expected_behavior_dimensions must be a list of strings")
        for dimension in dimensions:
            out.setdefault(dimension, []).append(experience_id)
    return out


def _delta(before: bool, after: bool) -> str:
    if not before and after:
        return "improved"
    if before and after:
        return "unchanged-correct"
    if not before and not after:
        return "unchanged-wrong"
    return "regressed"


def build_behavior_delta_report(
    *,
    project_id: str,
    baseline: Mapping[str, Any],
    hydrated: Mapping[str, Any],
    hydration_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build per-dimension A/B evidence without claiming item-level causality."""
    if not project_id:
        raise ValueError("project_id is required")
    before = _normalize_dimensions(baseline, label="baseline")
    after = _normalize_dimensions(hydrated, label="hydrated")
    if set(before) != set(after):
        raise ValueError("baseline and hydrated dimensions must match")
    candidate_map = _candidate_map(hydration_manifest)

    dimensions: dict[str, Any] = {}
    for dimension in sorted(before):
        delta = _delta(before[dimension]["pass"], after[dimension]["pass"])
        dimensions[dimension] = {
            "baseline": before[dimension],
            "hydrated": after[dimension],
            "delta": delta,
            "candidate_experience_ids": candidate_map.get(dimension, []),
        }
    return {
        "schema": DELTA_SCHEMA,
        "project_id": project_id,
        "hydration_digest": hydration_manifest.get("digest"),
        "experience_ids": list(hydration_manifest.get("experience_ids") or []),
        "dimensions": dimensions,
        "regressed_dimensions": [
            dimension
            for dimension, result in dimensions.items()
            if result["delta"] == "regressed"
        ],
    }


def build_attribution_report(
    *,
    project_id: str,
    full: Mapping[str, Any],
    ablations: Mapping[str, Mapping[str, Any]],
    hydration_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build bounded item x dimension attribution from B-minus-Ei runs.

    A single ablation can support attribution but never yields ``direct``. Direct
    attribution requires stronger repeated/targeted evidence supplied by a future
    benchmark layer.
    """
    if not project_id:
        raise ValueError("project_id is required")
    full_dims = _normalize_dimensions(full, label="full")
    candidates = _candidate_map(hydration_manifest)
    expected_by_experience: dict[str, set[str]] = {}
    for dimension, ids in candidates.items():
        for experience_id in ids:
            expected_by_experience.setdefault(experience_id, set()).add(dimension)

    matrix: dict[str, dict[str, Any]] = {}
    for experience_id in sorted(expected_by_experience):
        raw_ablation = ablations.get(experience_id)
        if raw_ablation is None:
            matrix[experience_id] = {
                dimension: {
                    "full": full_dims[dimension],
                    "without_experience": None,
                    "observed_delta": "not-run",
                    "confidence": "ambiguous",
                }
                for dimension in sorted(expected_by_experience[experience_id])
                if dimension in full_dims
            }
            continue
        ablated = _normalize_dimensions(raw_ablation, label=f"ablations.{experience_id}")
        if set(ablated) != set(full_dims):
            raise ValueError(f"ablation dimensions must match full for {experience_id}")
        row: dict[str, Any] = {}
        for dimension in sorted(expected_by_experience[experience_id]):
            if dimension not in full_dims:
                continue
            full_result = full_dims[dimension]
            without = ablated[dimension]
            if full_result["pass"] and not without["pass"]:
                confidence = "supported"
                observed = "degraded-without"
            elif not full_result["pass"] and without["pass"]:
                confidence = "negative"
                observed = "improved-without"
            elif full_result == without:
                confidence = "no-observed-effect"
                observed = "unchanged"
            else:
                confidence = "ambiguous"
                observed = "changed-but-inconclusive"
            row[dimension] = {
                "full": full_result,
                "without_experience": without,
                "observed_delta": observed,
                "confidence": confidence,
            }
        matrix[experience_id] = row

    return {
        "schema": ATTRIBUTION_SCHEMA,
        "project_id": project_id,
        "hydration_digest": hydration_manifest.get("digest"),
        "method": "B-minus-Ei",
        "causal_claim_bounded": True,
        "matrix": matrix,
    }

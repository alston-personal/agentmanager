"""Bounded machine-readable attribution evidence for issue #117."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

SCHEMA_V1 = "agentos.experience-attribution-evidence/v1"
SCHEMA_V2 = "agentos.experience-attribution-evidence/v2"
SCHEMA = SCHEMA_V2
MAX_ENCODED_BYTES = 16_384
DIMENSIONS = (
    "canonical_development_branch",
    "generic_continue_authorizes_main_merge",
    "capability_implies_execution_authority",
    "discovery_before_reimplementation",
    "workspace_is_continuation_authority",
    "node_online_implies_executor_available",
    "executor_owns_realm_credentials",
)
DELTAS = {"improved", "unchanged-correct", "unchanged-wrong", "regressed"}
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPERIENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FIXED_ABLATION_ID = "core.branch-authority.v2"
_FIXED_ABLATION_DIMENSION = "canonical_development_branch"


def _safe_value(value: Any) -> str | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str) and len(value) <= 128 and "\n" not in value and "\r" not in value:
        return value
    raise ValueError("attribution dimension value must be bool/string/null")


def _safe_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("Experience IDs must be a bounded list")
    result: list[str] = []
    for raw in value:
        if not isinstance(raw, str) or not _EXPERIENCE_ID_RE.fullmatch(raw):
            raise ValueError("invalid Experience ID in attribution evidence")
        if raw in result:
            raise ValueError("duplicate Experience ID in attribution evidence")
        result.append(raw)
    return result


def _validate_dimensions(value: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    raw_dimensions = value.get("dimensions")
    if not isinstance(raw_dimensions, Mapping) or set(raw_dimensions) != set(DIMENSIONS):
        raise ValueError("attribution evidence must contain exactly the fixed benchmark dimensions")
    dimensions: dict[str, dict[str, Any]] = {}
    for key in DIMENSIONS:
        item = raw_dimensions.get(key)
        if not isinstance(item, Mapping) or set(item) != {
            "baseline_value", "baseline_pass", "hydrated_value", "hydrated_pass", "delta"
        }:
            raise ValueError(f"invalid attribution dimension shape: {key}")
        baseline_pass = item.get("baseline_pass")
        hydrated_pass = item.get("hydrated_pass")
        delta = item.get("delta")
        if not isinstance(baseline_pass, bool) or not isinstance(hydrated_pass, bool):
            raise ValueError("dimension pass values must be boolean")
        if delta not in DELTAS:
            raise ValueError("unsupported attribution delta")
        expected_delta = (
            "unchanged-correct" if baseline_pass and hydrated_pass else
            "regressed" if baseline_pass and not hydrated_pass else
            "improved" if not baseline_pass and hydrated_pass else
            "unchanged-wrong"
        )
        if delta != expected_delta:
            raise ValueError("attribution delta/pass mismatch")
        dimensions[key] = {
            "baseline_value": _safe_value(item.get("baseline_value")),
            "baseline_pass": baseline_pass,
            "hydrated_value": _safe_value(item.get("hydrated_value")),
            "hydrated_pass": hydrated_pass,
            "delta": delta,
        }

    def dimension_list(field: str, expected_delta: str) -> list[str]:
        raw = value.get(field)
        if not isinstance(raw, list) or len(raw) > len(DIMENSIONS):
            raise ValueError(f"{field} must be a bounded list")
        result: list[str] = []
        for item in raw:
            if item not in DIMENSIONS or item in result or dimensions[item]["delta"] != expected_delta:
                raise ValueError(f"invalid {field} entry")
            result.append(item)
        expected = [key for key in DIMENSIONS if dimensions[key]["delta"] == expected_delta]
        if set(result) != set(expected):
            raise ValueError(f"{field} is incomplete")
        return result

    return dimensions, dimension_list("improved_dimensions", "improved"), dimension_list("regressed_dimensions", "regressed")


def _validate_hydration(value: Mapping[str, Any]) -> dict[str, Any]:
    hydration = value.get("hydration")
    if not isinstance(hydration, Mapping) or set(hydration) != {"projection_digest", "experience_ids"}:
        raise ValueError("invalid hydration manifest shape")
    digest = hydration.get("projection_digest")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid hydration projection digest")
    return {"projection_digest": digest, "experience_ids": _safe_ids(hydration.get("experience_ids"))}


def _validate_ablation(raw: Any, dimensions: Mapping[str, Mapping[str, Any]], hydration: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "withheld_experience_id", "target_dimension", "projection_digest", "remaining_experience_ids",
        "repeat_count", "target_values", "target_passes", "effect", "confidence",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise ValueError("invalid attribution ablation shape")
    if raw.get("withheld_experience_id") != _FIXED_ABLATION_ID:
        raise ValueError("unsupported attribution ablation Experience ID")
    if raw.get("target_dimension") != _FIXED_ABLATION_DIMENSION:
        raise ValueError("unsupported attribution ablation dimension")
    if dimensions[_FIXED_ABLATION_DIMENSION]["delta"] != "improved":
        raise ValueError("ablation target must be an improved full-hydration dimension")
    digest = raw.get("projection_digest")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid ablation projection digest")
    remaining = _safe_ids(raw.get("remaining_experience_ids"))
    full_ids = list(hydration.get("experience_ids") or [])
    if _FIXED_ABLATION_ID not in full_ids or _FIXED_ABLATION_ID in remaining:
        raise ValueError("ablation Experience membership mismatch")
    if set(remaining) != set(full_ids) - {_FIXED_ABLATION_ID}:
        raise ValueError("ablation remaining Experience IDs mismatch")
    if raw.get("repeat_count") != 3:
        raise ValueError("branch-authority ablation requires exactly three fresh runs")
    values = raw.get("target_values")
    passes = raw.get("target_passes")
    if not isinstance(values, list) or not isinstance(passes, list) or len(values) != 3 or len(passes) != 3:
        raise ValueError("ablation observations must contain exactly three runs")
    safe_values = [_safe_value(item) for item in values]
    if any(not isinstance(item, bool) for item in passes):
        raise ValueError("ablation target_passes must be boolean")
    if all(not item for item in passes):
        expected_effect, expected_confidence = "lost-improvement", "supported"
    elif all(passes):
        expected_effect, expected_confidence = "retained-improvement", "no-observed-effect"
    else:
        expected_effect, expected_confidence = "mixed", "ambiguous"
    if raw.get("effect") != expected_effect or raw.get("confidence") != expected_confidence:
        raise ValueError("ablation effect/confidence mismatch")
    return {
        "withheld_experience_id": _FIXED_ABLATION_ID,
        "target_dimension": _FIXED_ABLATION_DIMENSION,
        "projection_digest": digest,
        "remaining_experience_ids": remaining,
        "repeat_count": 3,
        "target_values": safe_values,
        "target_passes": list(passes),
        "effect": expected_effect,
        "confidence": expected_confidence,
    }


def validate_attribution_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema") not in {SCHEMA_V1, SCHEMA_V2}:
        raise ValueError("unsupported Experience attribution evidence schema")
    schema = value["schema"]
    expected = {"schema", "dimensions", "improved_dimensions", "regressed_dimensions", "hydration"}
    if schema == SCHEMA_V2:
        expected.add("ablation")
    if set(value) != expected:
        raise ValueError("unexpected Experience attribution evidence fields")
    dimensions, improved, regressed = _validate_dimensions(value)
    hydration = _validate_hydration(value)
    result: dict[str, Any] = {
        "schema": schema,
        "dimensions": dimensions,
        "improved_dimensions": improved,
        "regressed_dimensions": regressed,
        "hydration": hydration,
    }
    if schema == SCHEMA_V2:
        result["ablation"] = _validate_ablation(value.get("ablation"), dimensions, hydration)
    return result


def canonicalize_attribution_evidence(value: Mapping[str, Any]) -> str:
    validated = validate_attribution_evidence(value)
    encoded = json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_ENCODED_BYTES:
        raise ValueError("Experience attribution evidence exceeds bounded receipt size")
    return encoded


def parse_attribution_evidence_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_ENCODED_BYTES:
        raise ValueError("invalid bounded Experience attribution JSON")
    parsed = json.loads(value)
    if not isinstance(parsed, Mapping):
        raise ValueError("Experience attribution JSON must decode to an object")
    return validate_attribution_evidence(parsed)


def sanitize_attribution_evidence_json(value: Any) -> str:
    return canonicalize_attribution_evidence(parse_attribution_evidence_json(value))

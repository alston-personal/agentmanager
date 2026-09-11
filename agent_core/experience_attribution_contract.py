"""Bounded machine-readable attribution evidence for issue #117.

The executor-job transport deliberately does not allow arbitrary nested provider
results. This module validates the one structured #117 evidence payload and
canonicalizes it into a bounded JSON scalar before it may cross Action Relay / ONE.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

SCHEMA = "agentos.experience-attribution-evidence/v1"
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
DELTAS = {
    "improved",
    "unchanged-correct",
    "unchanged-wrong",
    "regressed",
}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPERIENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _safe_value(value: Any) -> str | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str) and len(value) <= 128 and "\n" not in value and "\r" not in value:
        return value
    raise ValueError("attribution dimension value must be bool/string/null")


def _safe_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("hydration experience_ids must be a bounded list")
    result: list[str] = []
    for raw in value:
        if not isinstance(raw, str) or not _EXPERIENCE_ID_RE.fullmatch(raw):
            raise ValueError("invalid Experience ID in attribution evidence")
        if raw in result:
            raise ValueError("duplicate Experience ID in attribution evidence")
        result.append(raw)
    return result


def validate_attribution_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema") != SCHEMA:
        raise ValueError("unsupported Experience attribution evidence schema")
    if set(value) != {"schema", "dimensions", "improved_dimensions", "regressed_dimensions", "hydration"}:
        raise ValueError("unexpected Experience attribution evidence fields")

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
            if item not in DIMENSIONS or item in result:
                raise ValueError(f"invalid {field} entry")
            if dimensions[item]["delta"] != expected_delta:
                raise ValueError(f"{field} disagrees with dimension delta")
            result.append(item)
        expected = [key for key in DIMENSIONS if dimensions[key]["delta"] == expected_delta]
        if set(result) != set(expected):
            raise ValueError(f"{field} is incomplete")
        return result

    improved = dimension_list("improved_dimensions", "improved")
    regressed = dimension_list("regressed_dimensions", "regressed")

    hydration = value.get("hydration")
    if not isinstance(hydration, Mapping) or set(hydration) != {"projection_digest", "experience_ids"}:
        raise ValueError("invalid hydration manifest shape")
    digest = hydration.get("projection_digest")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid hydration projection digest")
    experience_ids = _safe_ids(hydration.get("experience_ids"))

    return {
        "schema": SCHEMA,
        "dimensions": dimensions,
        "improved_dimensions": improved,
        "regressed_dimensions": regressed,
        "hydration": {
            "projection_digest": digest,
            "experience_ids": experience_ids,
        },
    }


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

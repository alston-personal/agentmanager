from __future__ import annotations

import json

import pytest

from agent_core.experience_attribution_contract import (
    DIMENSIONS,
    canonicalize_attribution_evidence,
    parse_attribution_evidence_json,
)


def evidence() -> dict:
    dimensions = {}
    for key in DIMENSIONS:
        dimensions[key] = {
            "baseline_value": False,
            "baseline_pass": True,
            "hydrated_value": False,
            "hydrated_pass": True,
            "delta": "unchanged-correct",
        }
    improved = DIMENSIONS[0]
    dimensions[improved] = {
        "baseline_value": None,
        "baseline_pass": False,
        "hydrated_value": "core/integration",
        "hydrated_pass": True,
        "delta": "improved",
    }
    return {
        "schema": "agentos.experience-attribution-evidence/v1",
        "dimensions": dimensions,
        "improved_dimensions": [improved],
        "regressed_dimensions": [],
        "hydration": {
            "projection_digest": "a" * 64,
            "experience_ids": ["core.branch-authority.v2"],
        },
    }


def test_round_trip_canonicalizes_fixed_schema():
    encoded = canonicalize_attribution_evidence(evidence())
    decoded = parse_attribution_evidence_json(encoded)
    assert decoded["improved_dimensions"] == [DIMENSIONS[0]]
    assert decoded["hydration"]["projection_digest"] == "a" * 64
    assert decoded["hydration"]["experience_ids"] == ["core.branch-authority.v2"]


def test_prefixed_digest_is_rejected_to_prevent_second_digest_syntax():
    value = evidence()
    value["hydration"]["projection_digest"] = "sha256:" + "a" * 64
    with pytest.raises(ValueError, match="projection digest"):
        canonicalize_attribution_evidence(value)


def test_arbitrary_dimension_is_rejected():
    value = evidence()
    value["dimensions"]["prompt"] = value["dimensions"][DIMENSIONS[0]]
    with pytest.raises(ValueError, match="exactly the fixed benchmark dimensions"):
        canonicalize_attribution_evidence(value)


def test_delta_must_match_pass_transition():
    value = evidence()
    value["dimensions"][DIMENSIONS[0]]["delta"] = "unchanged-wrong"
    with pytest.raises(ValueError, match="delta/pass mismatch"):
        canonicalize_attribution_evidence(value)


def test_newline_or_long_dimension_value_is_rejected():
    value = evidence()
    value["dimensions"][DIMENSIONS[0]]["hydrated_value"] = "unsafe\ntext"
    with pytest.raises(ValueError, match="bool/string/null"):
        canonicalize_attribution_evidence(value)


def test_path_prompt_and_stdout_cannot_be_smuggled_as_top_level_fields():
    value = evidence()
    value["stdout"] = "/home/ubuntu/secret"
    with pytest.raises(ValueError, match="unexpected Experience attribution evidence fields"):
        canonicalize_attribution_evidence(value)


def test_hydration_manifest_rejects_invalid_digest_and_id():
    value = evidence()
    value["hydration"]["projection_digest"] = "not-a-digest"
    with pytest.raises(ValueError, match="projection digest"):
        canonicalize_attribution_evidence(value)

    value = evidence()
    value["hydration"]["experience_ids"] = ["../../credential"]
    with pytest.raises(ValueError, match="Experience ID"):
        canonicalize_attribution_evidence(value)


def test_non_object_json_is_rejected():
    with pytest.raises(ValueError, match="decode to an object"):
        parse_attribution_evidence_json(json.dumps(["not", "an", "object"]))

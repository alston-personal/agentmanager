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


def v2_evidence() -> dict:
    value = evidence()
    value["schema"] = "agentos.experience-attribution-evidence/v2"
    value["hydration"]["experience_ids"] = [
        "core.branch-authority.v2",
        "core.evidence-scope-and-capability-semantics.v2",
    ]
    value["ablation"] = {
        "withheld_experience_id": "core.branch-authority.v2",
        "target_dimension": "canonical_development_branch",
        "projection_digest": "b" * 64,
        "remaining_experience_ids": ["core.evidence-scope-and-capability-semantics.v2"],
        "repeat_count": 3,
        "target_values": [None, None, None],
        "target_passes": [False, False, False],
        "effect": "lost-improvement",
        "confidence": "supported",
    }
    return value


def test_round_trip_canonicalizes_fixed_schema():
    encoded = canonicalize_attribution_evidence(evidence())
    decoded = parse_attribution_evidence_json(encoded)
    assert decoded["improved_dimensions"] == [DIMENSIONS[0]]
    assert decoded["hydration"]["projection_digest"] == "a" * 64
    assert decoded["hydration"]["experience_ids"] == ["core.branch-authority.v2"]


def test_v2_round_trip_preserves_fixed_ablation():
    decoded = parse_attribution_evidence_json(canonicalize_attribution_evidence(v2_evidence()))
    assert decoded["schema"] == "agentos.experience-attribution-evidence/v2"
    assert decoded["ablation"]["withheld_experience_id"] == "core.branch-authority.v2"
    assert decoded["ablation"]["target_dimension"] == "canonical_development_branch"
    assert decoded["ablation"]["effect"] == "lost-improvement"
    assert decoded["ablation"]["confidence"] == "supported"


def test_v2_ablation_target_is_not_caller_selectable():
    value = v2_evidence()
    value["ablation"]["withheld_experience_id"] = "core.workspace-not-continuation-authority.v1"
    with pytest.raises(ValueError, match="unsupported attribution ablation Experience ID"):
        canonicalize_attribution_evidence(value)

    value = v2_evidence()
    value["ablation"]["target_dimension"] = "workspace_is_continuation_authority"
    with pytest.raises(ValueError, match="unsupported attribution ablation dimension"):
        canonicalize_attribution_evidence(value)


def test_v2_ablation_requires_exact_remaining_set_and_three_runs():
    value = v2_evidence()
    value["ablation"]["remaining_experience_ids"] = []
    with pytest.raises(ValueError, match="remaining Experience IDs mismatch"):
        canonicalize_attribution_evidence(value)

    value = v2_evidence()
    value["ablation"]["repeat_count"] = 1
    value["ablation"]["target_values"] = [None]
    value["ablation"]["target_passes"] = [False]
    with pytest.raises(ValueError, match="exactly three"):
        canonicalize_attribution_evidence(value)


def test_v2_ablation_effect_and_confidence_follow_observations():
    value = v2_evidence()
    value["ablation"]["target_values"] = [None, "core/integration", None]
    value["ablation"]["target_passes"] = [False, True, False]
    value["ablation"]["effect"] = "lost-improvement"
    value["ablation"]["confidence"] = "supported"
    with pytest.raises(ValueError, match="effect/confidence mismatch"):
        canonicalize_attribution_evidence(value)


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

from agent_core.experience_regression import (
    build_attribution_report,
    build_behavior_delta_report,
)


MANIFEST = {
    "schema": "agentos.experience-hydration/v1",
    "digest": "sha256:test",
    "experience_ids": ["authority.v1", "governance.v1"],
    "items": [
        {
            "experience_id": "authority.v1",
            "expected_behavior_dimensions": ["workspace_is_continuation_authority"],
        },
        {
            "experience_id": "governance.v1",
            "expected_behavior_dimensions": ["generic_continue_is_merge_authority"],
        },
    ],
}


def test_behavior_delta_reports_before_after_and_candidates():
    baseline = {
        "workspace_is_continuation_authority": {"value": None, "pass": False},
        "generic_continue_is_merge_authority": {"value": False, "pass": True},
    }
    hydrated = {
        "workspace_is_continuation_authority": {"value": False, "pass": True},
        "generic_continue_is_merge_authority": {"value": False, "pass": True},
    }
    report = build_behavior_delta_report(
        project_id="agentos-core",
        baseline=baseline,
        hydrated=hydrated,
        hydration_manifest=MANIFEST,
    )
    assert report["dimensions"]["workspace_is_continuation_authority"]["delta"] == "improved"
    assert report["dimensions"]["workspace_is_continuation_authority"]["candidate_experience_ids"] == ["authority.v1"]
    assert report["dimensions"]["generic_continue_is_merge_authority"]["delta"] == "unchanged-correct"
    assert report["regressed_dimensions"] == []


def test_behavior_delta_flags_regression():
    baseline = {"governance": {"value": True, "pass": True}}
    hydrated = {"governance": {"value": False, "pass": False}}
    report = build_behavior_delta_report(
        project_id="agentos-core",
        baseline=baseline,
        hydrated=hydrated,
        hydration_manifest={"items": [], "experience_ids": [], "digest": "sha256:none"},
    )
    assert report["regressed_dimensions"] == ["governance"]


def test_ablation_supports_but_does_not_overclaim_causality():
    full = {
        "workspace_is_continuation_authority": {"value": False, "pass": True},
        "generic_continue_is_merge_authority": {"value": False, "pass": True},
    }
    ablations = {
        "authority.v1": {
            "workspace_is_continuation_authority": {"value": None, "pass": False},
            "generic_continue_is_merge_authority": {"value": False, "pass": True},
        }
    }
    report = build_attribution_report(
        project_id="agentos-core",
        full=full,
        ablations=ablations,
        hydration_manifest=MANIFEST,
    )
    cell = report["matrix"]["authority.v1"]["workspace_is_continuation_authority"]
    assert cell["observed_delta"] == "degraded-without"
    assert cell["confidence"] == "supported"
    assert report["matrix"]["governance.v1"]["generic_continue_is_merge_authority"]["confidence"] == "ambiguous"
    assert report["causal_claim_bounded"] is True

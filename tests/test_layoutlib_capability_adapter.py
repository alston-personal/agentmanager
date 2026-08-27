from capabilities.layoutlib import (
    PROFILE_CAPABILITY,
    correction_cost,
    make_profile_experience,
)


def test_correction_cost_is_domain_feedback_not_raw_history():
    metrics = {
        "walls_added": 2,
        "walls_deleted": 1,
        "erase_length_px": 50,
        "reanalyze_count": 2,
        "manual_parameter_changes": 1,
    }
    assert correction_cost(metrics) == 4.75


def test_profile_experience_contains_abstract_features_and_outcome():
    exp = make_profile_experience(
        node_id="browser-a",
        profile_features={"edge_density": 0.2, "background_luma": 240},
        policy_used={"threshold": 92, "min_wall_length_px": 16},
        correction_metrics={"walls_added": 0, "walls_deleted": 1},
        accepted=True,
        provenance={"session": "demo"},
    )
    assert exp.capability_id == PROFILE_CAPABILITY
    assert "profile_features" in exp.observation
    assert exp.outcome["correction_cost"] == 1.0
    assert exp.outcome["quality"] == 0.5
    assert "raw_image" not in exp.observation

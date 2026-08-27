from agentos_node.capability_runtime import (
    CapabilityExperience,
    CapabilityRuntime,
    non_regression_evaluator,
    weighted_numeric_profile_reducer,
)


def test_experience_deduplicates_and_consolidates_without_auto_promotion():
    rt = CapabilityRuntime()
    e1 = CapabilityExperience(
        capability_id="layoutlib.profile-detection",
        node_id="browser-a",
        observation={"profile": "scan-low-contrast"},
        policy_used={"threshold": 92, "min_wall_length_px": 16},
        outcome={"quality": 0.4, "correction_cost": 8},
    )
    e2 = CapabilityExperience(
        capability_id="layoutlib.profile-detection",
        node_id="browser-b",
        observation={"profile": "scan-low-contrast"},
        policy_used={"threshold": 86, "min_wall_length_px": 14},
        outcome={"quality": 0.9, "correction_cost": 2},
    )
    assert rt.observe(e1) == e1.experience_id
    assert rt.observe(e1) == e1.experience_id
    rt.observe(e2)
    assert len(rt.experiences("layoutlib.profile-detection")) == 2

    reducer = weighted_numeric_profile_reducer(("threshold", "min_wall_length_px"))
    result = rt.consolidate(
        "layoutlib.profile-detection", reducer, non_regression_evaluator
    )
    assert result.promotable is True
    assert result.candidate.state_kind == "candidate"
    assert rt.canonical("layoutlib.profile-detection") is None
    assert 86 < result.candidate.payload["policy"]["threshold"] < 92


def test_promotion_requires_explicit_authority_receipt():
    rt = CapabilityRuntime()
    for node, threshold in (("a", 90), ("b", 88)):
        rt.observe(
            CapabilityExperience(
                capability_id="layoutlib.profile-detection",
                node_id=node,
                observation={"kind": "clean-cad"},
                policy_used={"threshold": threshold},
                outcome={"quality": 0.9},
            )
        )
    result = rt.consolidate(
        "layoutlib.profile-detection",
        weighted_numeric_profile_reducer(("threshold",)),
        non_regression_evaluator,
    )
    assert result.promotable

    try:
        rt.promote(
            "layoutlib.profile-detection", approved=True, authority_receipt={}
        )
        assert False, "promotion without provenance must fail"
    except PermissionError:
        pass

    canonical = rt.promote(
        "layoutlib.profile-detection",
        approved=True,
        authority_receipt={"decision_id": "gov-1", "approved_by": "test"},
    )
    assert canonical.state_kind == "canonical"
    assert canonical.version == 1
    assert rt.canonical("layoutlib.profile-detection").state_id == canonical.state_id

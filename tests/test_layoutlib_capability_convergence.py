from agentos_node.capability_runtime import (
    CapabilityRuntime,
    non_regression_evaluator,
    weighted_numeric_profile_reducer,
)
from capabilities.layoutlib import PROFILE_CAPABILITY, make_profile_experience


def _exp(node_id: str, threshold: float, correction_cost_case: str):
    metrics_by_case = {
        "high": {"walls_added": 2, "walls_deleted": 1, "manual_parameter_changes": 1},
        "medium": {"walls_deleted": 1},
        "zero": {},
    }
    return make_profile_experience(
        node_id=node_id,
        profile_features={
            "background_luma": 240,
            "edge_density": 0.2,
            "contrast": 0.58,
        },
        policy_used={"threshold": threshold},
        correction_metrics=metrics_by_case[correction_cost_case],
        accepted=True,
        provenance={"experiment": "layoutlib-cross-node-bootstrap-v1"},
    )


def test_nodes_converge_to_capability_state_and_fresh_node_can_bootstrap():
    runtime = CapabilityRuntime()

    # Three independent nodes contribute experience to the capability owner.
    runtime.observe(_exp("browser-a", 92, "high"))
    runtime.observe(_exp("browser-b", 88, "medium"))
    runtime.observe(_exp("browser-c", 87, "zero"))

    result = runtime.consolidate(
        PROFILE_CAPABILITY,
        weighted_numeric_profile_reducer(["threshold"]),
        non_regression_evaluator,
    )

    assert result.promotable is True
    assert result.candidate.support == 3

    canonical = runtime.promote(
        PROFILE_CAPABILITY,
        approved=True,
        authority_receipt={
            "type": "test-governance-receipt",
            "experiment": "layoutlib-cross-node-bootstrap-v1",
        },
    )

    # Lower-correction experiences carry more weight, so the shared policy moves
    # away from node A's 92 and toward the successful 87/88 observations.
    learned_threshold = canonical.payload["policy"]["threshold"]
    assert 87.0 <= learned_threshold < 89.0

    # Node D has produced no local experience. It can still start from the
    # capability-owned canonical state. This is the minimum proof of shared
    # capability bootstrap rather than browser-local learning.
    node_d_local_experience_count = 0
    node_d_bootstrap = runtime.canonical(PROFILE_CAPABILITY)

    assert node_d_local_experience_count == 0
    assert node_d_bootstrap is not None
    assert node_d_bootstrap.state_kind == "canonical"
    assert node_d_bootstrap.payload["policy"]["threshold"] == learned_threshold


def test_capability_owner_deduplicates_replayed_experience():
    runtime = CapabilityRuntime()
    exp = _exp("browser-a", 88, "zero")

    first = runtime.observe(exp)
    second = runtime.observe(exp)

    assert first == second
    assert len(runtime.experiences(PROFILE_CAPABILITY)) == 1

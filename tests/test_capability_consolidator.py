from agentos_node.capability_consolidator import consolidate_profile
from agentos_node.capability_store import CapabilityStore


def _exp(eid, node, threshold, quality):
    return {
        "schema": "agentos.capability-experience/v1",
        "experience_id": eid,
        "capability_id": "layoutlib.profile-detection",
        "node_id": node,
        "observation": {"profile_features": {"edge_density": 0.2, "contrast": 0.5}},
        "policy_used": {"threshold": threshold, "min_wall_length_px": 16},
        "outcome": {"accepted": True, "correction_cost": 1 / max(quality, 0.01), "quality": quality},
        "provenance": {"experiment": "persisted-convergence-test"},
    }


def test_persisted_experience_consolidates_and_promotes(tmp_path):
    store = CapabilityStore(tmp_path)
    store.ingest(_exp("exp-a", "browser-a", 92, 0.25))
    store.ingest(_exp("exp-b", "browser-b", 88, 0.75))
    store.ingest(_exp("exp-c", "browser-c", 87, 1.0))

    result = consolidate_profile(
        tmp_path,
        promote=True,
        authority_receipt={"decision_id": "layoutlib-v0.7-test", "approved_by": "governed-test"},
    )

    assert result["promoted"] is True
    assert result["promotable"] is True
    assert result["experience_count"] == 3
    learned = result["canonical"]["payload"]["policy"]["threshold"]
    assert 87 <= learned < 89
    persisted = store.read_state("layoutlib.profile-detection", slot="canonical")
    assert persisted["state_kind"] == "canonical"
    assert persisted["payload"]["policy"]["threshold"] == learned


def test_single_experience_cannot_be_promoted(tmp_path):
    store = CapabilityStore(tmp_path)
    store.ingest(_exp("exp-a", "browser-a", 90, 1.0))
    try:
        consolidate_profile(
            tmp_path,
            promote=True,
            authority_receipt={"decision_id": "must-not-promote"},
        )
    except PermissionError as exc:
        assert "did not pass evaluator" in str(exc)
    else:
        raise AssertionError("single observation must not pass bootstrap evaluation")

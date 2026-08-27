from agentos_node.capability_store import CapabilityStore


def exp(experience_id="exp-1"):
    return {
        "schema": "agentos.capability-experience/v1",
        "experience_id": experience_id,
        "capability_id": "layoutlib.profile-detection",
        "node_id": "browser-a",
        "observation": {"profile_features": {"edge_density": 0.2}},
        "policy_used": {"threshold": 88},
        "outcome": {"accepted": True, "correction_cost": 1.0, "quality": 0.5},
        "provenance": {"source": "layoutlab-web"},
    }


def test_ingest_is_idempotent(tmp_path):
    store = CapabilityStore(tmp_path)
    first = store.ingest(exp())
    second = store.ingest(exp())
    assert first["accepted"] is True and first["duplicate"] is False
    assert second["accepted"] is True and second["duplicate"] is True
    assert len(store.experiences("layoutlib.profile-detection")) == 1


def test_same_id_with_different_payload_is_rejected(tmp_path):
    store = CapabilityStore(tmp_path)
    store.ingest(exp())
    changed = exp()
    changed["policy_used"] = {"threshold": 92}
    try:
        store.ingest(changed)
    except ValueError as exc:
        assert "collision" in str(exc)
    else:
        raise AssertionError("collision must be rejected")


def test_raw_image_telemetry_is_rejected(tmp_path):
    store = CapabilityStore(tmp_path)
    value = exp()
    value["observation"]["raw_image"] = "base64..."
    try:
        store.ingest(value)
    except ValueError as exc:
        assert "raw image" in str(exc)
    else:
        raise AssertionError("raw image telemetry must be rejected")


def test_canonical_state_round_trip(tmp_path):
    store = CapabilityStore(tmp_path)
    state = {
        "schema": "agentos.capability-state/v1",
        "state_id": "capstate-1",
        "capability_id": "layoutlib.profile-detection",
        "version": 3,
        "state_kind": "canonical",
        "support": 12,
        "confidence": 0.8,
        "payload": {"policy": {"threshold": 88, "min_wall_length_px": 16}},
        "evidence_ids": ["exp-1"],
    }
    store.write_state(state, slot="canonical")
    assert store.read_state("layoutlib.profile-detection")["payload"]["policy"]["threshold"] == 88

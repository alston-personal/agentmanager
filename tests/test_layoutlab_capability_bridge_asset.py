from pathlib import Path


BRIDGE = Path("web_assets/layoutlab-capability-bridge-v0.7.js")


def test_completion_is_capability_learning_boundary():
    text = BRIDGE.read_text(encoding="utf-8")
    assert "finishModel" in text
    assert "assimilateLearning=()=>{}" in text
    assert "originalAssimilate" in text
    assert "correction_cost" in text
    assert "layoutlib.capability.pending.v1" in text


def test_bridge_exposes_fresh_node_canonical_policy_hook():
    text = BRIDGE.read_text(encoding="utf-8")
    assert "applyCanonicalPolicy" in text
    assert "agentos_canonical" in text
    assert "pendingExperiences" in text
    assert "drainPendingExperiences" in text


def test_bridge_does_not_queue_raw_image_data():
    text = BRIDGE.read_text(encoding="utf-8")
    assert "raw_image" not in text
    assert "imageData" not in text
    assert "toDataURL" not in text


def test_v07_product_identity_and_robust_selected_wall_delete_are_present():
    text = BRIDGE.read_text(encoding="utf-8")
    assert "Layout Lab v0.7 · AgentOS closed loop" in text
    assert "robustDeleteWallsById" in text
    assert "start_px" in text and "end_px" in text
    assert "endpointDistance" in text
    assert "edit.removed" in text

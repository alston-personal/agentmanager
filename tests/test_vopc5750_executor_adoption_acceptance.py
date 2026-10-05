from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "vopc5750-executor-adoption-acceptance.yml"


def test_vopc5750_acceptance_uses_read_only_generation_gate():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "runtime-generation-gate:" in text
    assert "agentos.relay status" in text
    assert "relay_status_antigravity_source_commit" in text
    assert "relay_status_action_source_commit" in text
    assert "agentos.runtime" not in text
    assert "operation: repair" not in text
    assert "needs: runtime-generation-gate" in text


def test_vopc5750_acceptance_keeps_bounded_node_sequence():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "capability: node.realm" in text
    assert "operation: inspect" in text
    assert "capability: node.executor" in text
    assert "operation: reconcile" in text
    assert 'payload_json: \'{"node_id":"vopc5750"}\'' in text

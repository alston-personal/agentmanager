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


def test_vopc5750_generation_gate_accepts_only_converged_ancestor_runtime():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "fetch-depth: 2" in text
    assert "git merge-base --is-ancestor" in text
    assert 'git diff --name-only "$live_commit" "$GITHUB_SHA"' in text
    for path in (
        "agentos_node/bootstrap_control.py",
        "agentos_node/bootstrap_scheduler.py",
        "agent_core/runner_window.py",
        "agent_core/realm_server.py",
        "scripts/install_bootstrap_scheduler_user.sh",
    ):
        assert path in text
    assert "relay_status_antigravity_source_commit" in text
    assert "relay_status_action_source_commit" in text

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_oracle_exec_install_reuses_governed_existing_action():
    from agent_core.runner_window import resolve_intent
    from agentos_node.bootstrap_control import ACTION_INSTALL_ORACLE_EXEC
    source_commit = "a" * 40
    intent, params = resolve_intent("node.runtime", "oracle-exec.install", source_commit=source_commit, payload={})
    assert intent.action == ACTION_INSTALL_ORACLE_EXEC
    assert params["source_commit"] == source_commit


def test_oracle_exec_install_blocks_untrusted_payload():
    import pytest
    from agent_core.runner_window import resolve_intent
    with pytest.raises((ValueError, TypeError)):
        resolve_intent("node.runtime", "oracle-exec.install", source_commit="a" * 40, payload={"node_id": "vopc5750"})


def test_oracle_exec_runtime_installer_pinned_and_fixed():
    source = (ROOT / "agentos_node/bootstrap_control.py").read_text()
    assert '"scripts/install_thin_client_linux_oracle.sh"' in source
    installer = (ROOT / "scripts/install_thin_client_linux_oracle.sh").read_text()
    assert 'AGENTOS_SOURCE_COMMIT' in installer
    assert 'agentos_oracle_exec_runtime_provenance=PASS' in installer

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_golden_path_deploy_discovery_contract():
    intent = (ROOT / "agent_core/runner_window.py").read_text()
    bootstrap = (ROOT / "agentos_node/bootstrap_control.py").read_text()
    repair = (ROOT / "scripts/repair_antigravity_relay_user.sh").read_text()
    installer = (ROOT / "scripts/install_action_relay_user.sh").read_text()
    workflow = (ROOT / ".github/workflows/core-integration-runtime-self-converge-20261007.yml").read_text()
    assert 'RunnerWindowIntent("agentos.runtime", "repair", bc.ACTION_REPAIR_TRANSPORT)' in intent
    assert 'scripts/repair_antigravity_relay_user.sh' in bootstrap
    assert 'scripts/install_action_relay_user.sh' in repair
    assert 'AGENTOS_ACTION_SOURCE_COMMIT' in repair
    assert 'AGENTOS_ACTION_SOURCE_REF' in repair
    assert 'action_relay_install=PASS' in installer
    assert 'audience=agentos-scheduler' in workflow
    assert '"operation":"repair"' in workflow
    assert 'action_relay_install=PASS' in workflow


def test_golden_path_documented_capability_vs_carrier():
    doc = (ROOT / "docs/GOLDEN_PATH_RUNTIME_REPAIR_DISCOVERY.md").read_text()
    for marker in ("Runner Window", "authorized carrier", "node.runtime/converge",
                   "action_relay_install=PASS", "core/integration", "main"):
        assert marker in doc

from pathlib import Path


def test_control_inbox_reconcile_is_isolated_from_realm_runtime():
    script = Path("scripts/reconcile_control_inbox_runtime_user.sh").read_text(encoding="utf-8")
    assert "agentos-control-inbox.service" in script
    assert "control_inbox_safe_reconcile=PASS" in script
    assert "control_inbox_realm_restart=NO" in script
    assert "agentos.executor.job" in script
    assert "agentos-realm-fabric.service" not in "\n".join(
        line for line in script.splitlines() if "After=" not in line and "Requires=" not in line
    )
    for forbidden in (
        "node_registry.py",
        "node_bootstrap.py",
        "realm_fabric.py",
        "controller_api.py",
        "realm_server.py",
        "realm_cli.py",
    ):
        assert forbidden not in script


def test_bootstrap_control_uses_isolated_reconcile_script():
    text = Path("agentos_node/bootstrap_control.py").read_text(encoding="utf-8")
    block = text.split("if action == ACTION_RECONCILE_CONTROL_INBOX:", 1)[1].split(
        "if action == ACTION_DEPLOY_REALM_GATEWAY:", 1
    )[0]
    assert "scripts/reconcile_control_inbox_runtime_user.sh" in block
    assert "scripts/install_control_inbox_bridge_user.sh" not in block


def test_realm_core_carrier_reconciles_isolated_control_inbox():
    workflow = Path(".github/workflows/deploy-realm-fabric-core.yml").read_text(encoding="utf-8")
    assert "scripts/reconcile_control_inbox_runtime_user.sh" in workflow
    assert "control_inbox_isolated_reconcile=PASS" in workflow
    assert "AGENTOS_SOURCE_COMMIT=\"$SHA\"" in workflow


def test_control_inbox_env_rebuild_preserves_runtime_reconnect_action():
    script = Path("scripts/repair_control_inbox_github_auth_user.sh").read_text(encoding="utf-8")
    assert "node.runtime.converge.inspect" in script

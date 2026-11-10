from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml"
INSTALLER=ROOT/"scripts/install_systemd_user.sh"

def test_immutable_core_deploy_restores_only_previously_active_s4_surface():
    text=WORKFLOW.read_text(encoding="utf-8")
    assert "S4_RESTORE=0" in text
    assert "grep -Fxq 'agentos-employee-wake-node.service' \"$BACKUP/active-services\"" in text
    assert "grep -Fxq 'agentos-employee-worker-host.service' \"$BACKUP/active-services\"" in text
    assert '|| [ "$WORKER_SYSTEM_ACTIVE" = 1 ]' in text
    assert 'AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT="$S4_RESTORE"' in text
    assert "AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct" in text

def test_supervisor_installer_requires_explicit_s4_flag_and_realm_state():
    text=INSTALLER.read_text(encoding="utf-8")
    assert 'if [ "${AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT:-0}" = "1" ]; then' in text
    assert 'test -f "$DATA_ROOT/realm/fabric.json"' in text
    assert 'test -f "$DATA_ROOT/realm/nodes.json"' in text
    assert "AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct" in text
    assert "AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled" in text

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_action_relay_user.sh"
PUBLISHER = ROOT / "scripts" / "publish_action_relay_capability.py"


def test_installer_uses_fixed_agentos_group_context_for_capability_publish():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "/usr/bin/sg agentos -c" in text
    assert "publish_action_relay_capability.py" in text
    assert "--marker '$CAPABILITY_MARKER'" in text
    assert "--source-ref '$SOURCE_REF'" in text
    assert "--source-commit '$SOURCE_COMMIT'" in text
    assert "action_relay_capability_group_context=PASS" in text


def test_publisher_has_no_generic_execution_surface():
    text = PUBLISHER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "shell=True" not in text
    assert "capability_marker_payload" in text


def test_action_relay_exec_pins_exact_runtime_import_path_inside_sg():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'cd "$RUNTIME_ROOT" && exec /usr/bin/env PYTHONPATH="$RUNTIME_ROOT"' in text
    assert 'AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT="$SOURCE_COMMIT"' in text
    assert '/usr/bin/python3 -m agentos_node.executor_job_action_relay' in text


def test_installer_converges_to_one_exact_generation_consumer_fail_closed():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'systemctl --user stop agentos-action-relay.service' in text
    assert 'processing did not drain before consumer cleanup' in text
    assert 'action_relay_processing_drain=PASS' in text
    assert 'relay_consumer_pids()' in text
    assert 'cat "/proc/$pid/comm"' in text
    assert 'agentos_node\\.(action_relay|executor_job_action_relay)' in text
    assert 'action_relay_prior_consumers_cleared=PASS' in text
    assert 'expected exactly one canonical Action Relay consumer' in text
    assert 'AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT=$SOURCE_COMMIT' in text
    assert 'action_relay_single_consumer=PASS' in text
    assert 'action_relay_runtime_generation_env=PASS' in text


def test_installer_cutover_is_fresh_node_safe_zombie_safe_and_stage_specific():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'if [ -f "$UNIT" ]; then' in text
    assert 'managed Action Relay service remained active after stop' in text
    assert 'awk \'{print $3}\' "/proc/$pid/stat"' in text
    assert '[ "$state" = "Z" ] && continue' in text
    for code in ("61", "62", "63", "64", "65", "66", "67"):
        assert f"exit {code}" in text


def test_generation_env_check_does_not_use_grep_q_pipeline_under_pipefail():
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'relay_env_check=$(mktemp)' in text
    assert 'tr \'\\0\' \'\\n\' < "/proc/$relay_pid/environ" > "$relay_env_check"' in text
    assert '| grep -Fxq "AGENTOS_ACTION_RUNTIME_SOURCE_REF=' not in text
    assert '| grep -Fxq "AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT=' not in text

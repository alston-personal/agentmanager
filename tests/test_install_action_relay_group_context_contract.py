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
    assert 'processing did not drain before managed stop' in text
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
    for code in ("61", "62", "63", "64", "65", "66", "67", "68", "69"):
        assert f"exit {code}" in text


def test_generation_check_does_not_read_cross_uid_proc_environ():
    text = INSTALLER.read_text(encoding="utf-8")
    assert '"/proc/$relay_pid/environ"' not in text
    assert "systemctl --user show agentos-action-relay.service -p Environment --value" in text
    assert "systemctl --user show agentos-action-relay.service -p WorkingDirectory --value" in text
    assert 'git -C "$RUNTIME_ROOT" rev-parse HEAD' in text
    assert "action_relay_runtime_generation_unit=PASS" in text


def test_installer_drains_processing_before_stopping_managed_worker():
    text = INSTALLER.read_text(encoding="utf-8")
    drain = text.index("action_relay_processing_drain=PASS")
    stop = text.index("systemctl --user stop agentos-action-relay.service")
    assert drain < stop
    assert "action_relay_processing_handoff=PASS" in text
    assert "processing appeared during drain/stop handoff" in text


def test_installer_recovers_stale_processing_only_when_managed_worker_is_offline():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "if ! systemctl --user is-active --quiet agentos-action-relay.service" in text
    assert "AntigravityRelayWorker" in text
    assert "reconcile_stranded_processing(stale_after=600)" in text
    assert "action_relay_offline_stranded_reconcile=PASS" in text
    assert "inactive Action Relay stranded processing did not reach safe reconciliation threshold" in text


def test_installer_reconciles_stale_processing_during_normal_drain():
    text = INSTALLER.read_text(encoding="utf-8")
    marker = "processing_clear=0"
    block = text.split(marker, 1)[1].split('if [ "$processing_clear" -ne 1 ]', 1)[0]
    assert "reconcile_stranded_processing(stale_after=600)" in block
    assert "UNKNOWN_SIDE_EFFECT" in block

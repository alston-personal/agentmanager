from pathlib import Path


def test_persona_timer_install_runs_live_acceptance_cycle():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"install_persona_pdca_timer_user.sh").read_text(encoding="utf-8")
    assert "systemctl --user start agentos-persona-pdca-heartbeat.service" in text
    assert "persona_pdca_install_live_cycle=PASS" in text
    assert "OnUnitActiveSec=60min" in text


def test_persona_timer_uses_canonical_versioned_heartbeat_runtime():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"install_persona_pdca_timer_user.sh").read_text(encoding="utf-8")
    assert 'CANONICAL_HEARTBEAT="$BIN/agentos-persona-pdca-heartbeat-v2"' in text
    assert 'install -m 0755 "$SOURCE_RUNNER" "$CANONICAL_HEARTBEAT"' in text
    assert 'cmp -s "$SOURCE_RUNNER" "$CANONICAL_HEARTBEAT"' in text
    assert 'ExecStart=$CANONICAL_HEARTBEAT' in text
    assert 'systemctl --user show -p ExecStart --value agentos-persona-pdca-heartbeat.service' in text


def test_installer_does_not_advance_autonomous_heartbeat():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"install_persona_pdca_timer_user.sh").read_text(encoding="utf-8")
    assert 'systemctl --user start agentos-persona-pdca-heartbeat.service' not in text
    assert 'persona_pdca_install_live_cycle=SKIPPED' in text
    assert 'installer_must_not_advance_autonomous_cycle' in text

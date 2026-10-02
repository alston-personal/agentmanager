from pathlib import Path


def test_oursong_activation_materializes_exact_persona_release():
    text = Path("scripts/activate_oursong_persona_user.sh").read_text(encoding="utf-8")
    assert "AGENTOS_SOURCE_COMMIT" in text
    assert 'git -C "${REPO}" archive "${SOURCE_COMMIT}"' in text
    assert "persona-social/releases" in text
    assert "AGENTOS_PERSONA_PDCA_TICK_SCRIPT=${RELEASE}/scripts/persona_pdca_tick_user.py" in text
    assert "AGENTOS_PERSONA_SOCIAL_LOOP_SCRIPT=${RELEASE}/scripts/mio_persona_social_loop_user.py" in text
    assert "AGENTOS_PERSONA_PDCA_SYNC_SCRIPT=${RELEASE}/scripts/sync_persona_pdca_social_outcome_user.py" in text
    assert "oursong_runtime_release=${RELEASE}" in text


def test_persona_timer_uses_profile_pinned_script_paths():
    text = Path("scripts/install_persona_social_timer_user.sh").read_text(encoding="utf-8")
    tick = "ExecStart=/usr/bin/python3 ${AGENTOS_PERSONA_PDCA_TICK_SCRIPT}"
    social = "ExecStart=/usr/bin/python3 ${AGENTOS_PERSONA_SOCIAL_LOOP_SCRIPT}"
    assert tick in text
    assert social in text
    assert text.index(tick) < text.index(social)
    assert "ExecStartPost=/usr/bin/python3 ${AGENTOS_PERSONA_PDCA_SYNC_SCRIPT}" in text
    assert "%h/agentmanager/scripts/mio_persona_social_loop_user.py" not in text
    assert "%h/agentmanager/scripts/sync_persona_pdca_social_outcome_user.py" not in text

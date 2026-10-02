from pathlib import Path


def test_persona_timer_install_runs_live_acceptance_cycle():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"install_persona_pdca_timer_user.sh").read_text(encoding="utf-8")
    assert "systemctl --user start agentos-persona-pdca-heartbeat.service" in text
    assert "persona_pdca_install_live_cycle=PASS" in text
    assert "OnUnitActiveSec=60min" in text

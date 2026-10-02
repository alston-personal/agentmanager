from pathlib import Path


def test_heartbeat_isolates_optional_social_failures():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_persona_pdca_heartbeat_user.sh").read_text(encoding="utf-8")
    assert "run_optional reply_intent" in text
    assert "run_optional post_intent" in text
    assert "persona_optional_social_executor=DEGRADED" in text
    observer=text.index('python3 "$PUBLIC_ACTIVITY_PUBLISHER"')
    persist=text.index('cd "$DATA_REPO"')
    assert observer < persist


def test_reply_reasoner_timeout_is_structured_defer():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"persona_reply_intent_generator.py").read_text(encoding="utf-8")
    assert "except subprocess.TimeoutExpired:" in text
    assert '"persona_reasoning_timeout"' in text

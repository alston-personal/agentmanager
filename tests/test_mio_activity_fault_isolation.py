from pathlib import Path


def test_core_heartbeat_projects_observer_before_persisting():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_persona_pdca_heartbeat_user.sh").read_text(encoding="utf-8")
    # #782 moved optional social work out of this lane altogether.
    observer=text.index('python3 "$PUBLIC_ACTIVITY_PUBLISHER"')
    persist=text.index('cd "$DATA_REPO"')
    assert observer < persist


def test_reply_reasoner_timeout_is_structured_defer():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"persona_reply_intent_generator.py").read_text(encoding="utf-8")
    assert "except subprocess.TimeoutExpired:" in text
    assert '"persona_reasoning_timeout"' in text


def test_core_heartbeat_has_no_social_reasoning_or_execution():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_persona_pdca_heartbeat_user.sh").read_text(encoding="utf-8")
    assert 'python3 "$INTERNAL_EXECUTOR"' in text
    assert 'python3 "$PUBLIC_ACTIVITY_PUBLISHER"' in text
    assert 'python3 "$REPLY_INTENT_GENERATOR" --persona-dir' not in text
    assert 'python3 "$POST_INTENT_GENERATOR" --persona-dir' not in text
    assert 'python3 "$SOCIAL_EXECUTOR" --persona-dir' not in text


def test_social_lane_owns_reply_and_post_intent_generation():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_persona_social_actions_user.sh").read_text(encoding="utf-8")
    assert 'python3 "$REPLY_INTENT_GENERATOR" --persona-dir "$ROOT"' in text
    assert 'python3 "$POST_INTENT_GENERATOR" --persona-dir "$ROOT"' in text
    assert 'python3 "$SOCIAL_EXECUTOR" --persona-dir "$ROOT"' in text


def test_core_heartbeat_fails_closed_on_stale_internal_activity():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_persona_pdca_heartbeat_user.sh").read_text(encoding="utf-8")
    internal=text.index('python3 "$INTERNAL_EXECUTOR"')
    integrity=text.index('persona_pdca_cognitive_integrity=PASS')
    publisher=text.index('python3 "$PUBLIC_ACTIVITY_PUBLISHER"')
    persist=text.index('cd "$DATA_REPO"')
    assert internal < integrity < publisher < persist
    assert '"error":"stale_activity_receipt"' in text
    assert 'int(activity.get("cycle",-1))==cycle' in text


def test_runtime_acceptance_requires_same_cycle_activity_receipt():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_persona_pdca_heartbeat_user.sh").read_text(encoding="utf-8")
    assert 'activity_ref=s.get("last_activity_receipt")' in text
    assert 'assert int(activity["cycle"])==int(s["cycle"])' in text

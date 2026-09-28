from pathlib import Path

s=Path('scripts/mio_persona_dm_decision_user.py').read_text(encoding='utf-8')

def test_dm_decision_requires_truth_boundary_and_relationship_context():
    assert 'no_false_autobiography' in s
    assert 'unknown_new_interaction' in s or 'relationship_status' in s
    assert 'deterministic_ir_fallback' in s
    assert "'decision':'no_reply'" in s

def test_travel_fallback_does_not_claim_real_trip():
    assert '沒有安排旅行耶，最近反而一直在想海邊跟散步這種小行程。你有去哪裡嗎？' in s
    assert '我去了' not in s
    assert '我剛從' not in s

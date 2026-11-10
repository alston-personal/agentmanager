from pathlib import Path

social=Path('scripts/mio_persona_social_loop_user.py').read_text(encoding='utf-8')
evolve=Path('scripts/evolve_mio_persona_ir_user.py').read_text(encoding='utf-8')
dm=Path('scripts/run_mio_dm_decision_user.sh').read_text(encoding='utf-8')

def test_private_dm_events_stay_out_of_public_persona_context():
    assert "visibility" in social
    assert "!='private'" in social or '!= "private"' in social

def test_private_dm_events_stay_out_of_global_ir_reducer():
    assert "visibility" in evolve
    assert '!= "private"' in evolve

def test_dm_decision_loads_relationship_context():
    assert 'relationships/threads' in dm
    assert 'relationship_context' in dm
    assert 'last_inbound' in dm
    assert 'last_outbound' in dm

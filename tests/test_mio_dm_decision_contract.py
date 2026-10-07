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


def test_mio_oursong_oracle_cycle_is_bounded_and_readback_guarded():
    cycle=Path('scripts/mio_oursong_dm_oracle_cycle_user.py').read_text(encoding='utf-8')
    assert 'max_auto_hops=2' in cycle
    assert 'cooldown_seconds=120' in cycle
    assert 'record_consumed' in cycle
    assert 'record_auto_reply' in cycle
    assert 'mio_oursong_dm_readback=PASS' in cycle
    assert 'SEND_UNVERIFIED' in cycle
    assert 'http://127.0.0.1:9222' in Path('scripts/mio_dm_oracle_oursong_acceptance.py').read_text(encoding='utf-8')


def test_mio_oursong_dm_timer_is_five_minutes_and_does_not_force_reply():
    installer=Path('scripts/install_mio_oursong_dm_timer_user.sh').read_text(encoding='utf-8')
    assert 'OnUnitActiveSec=5min' in installer
    assert 'mio-oursong-dm-autonomous.service' in installer
    assert 'max_hops_2_cooldown_120s' in installer


def test_mio_oursong_dm_runtime_materializes_loop_guard():
    cycle=Path('scripts/mio_oursong_dm_oracle_cycle_user.py').read_text(encoding='utf-8')
    installer=Path('scripts/install_mio_oursong_dm_timer_user.sh').read_text(encoding='utf-8')
    assert 'from dm_loop_guard_runtime import' in cycle
    assert 'SOURCE_GUARD="${2:-}"' in installer
    assert 'dm_loop_guard_runtime.py' in installer
    assert 'agentos_node/social/dm_loop_guard.py' not in installer


def test_mio_oursong_dm_cycle_persists_bounded_receipts():
    cycle=Path('scripts/mio_oursong_dm_oracle_cycle_user.py').read_text(encoding='utf-8')
    assert 'agentos.mio-dm-cycle-receipt/v1' in cycle
    assert 'dm-receipts' in cycle
    for status in ('ALIVE_IDLE','AUTH_REQUIRED','DEGRADED','PASS_NO_ACTION','PASS_NO_REPLY','PASS_REPLY'):
        assert f'"{status}"' in cycle
    assert 'message_id=mid' in cycle
    assert 'readback="PASS"' in cycle

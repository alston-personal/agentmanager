from pathlib import Path

REPO=Path(__file__).resolve().parents[1]

def test_mio_dm_cycle_retries_transient_cdp_open_failures():
    text=(REPO/"scripts"/"mio_oursong_dm_oracle_cycle_user.py").read_text(encoding="utf-8")
    assert 'for attempt in range(1,4):' in text
    assert 'mio_oursong_dm_cycle_cdp_open_retry=' in text
    assert 'reason="CDP_OPEN_FAILED"' in text
    assert 'mio_oursong_dm_cycle_error_type=' in text
    assert 'return 4' in text

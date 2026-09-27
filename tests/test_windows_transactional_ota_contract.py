from pathlib import Path
p=Path('scripts/windows/transactional_ota.ps1')
s=p.read_text(encoding='utf-8')
required=['versions','last-known-good.json','candidate_import=PASS','Move-Item -Force $next $launcher','candidate-validated','agentos_ota_rollback=PASS','agentos_ota_post_switch=PASS','active-accepted']
def test_contract():
    for marker in required:
        assert marker in s, marker
    assert s.index('candidate_import=PASS') < s.index('Move-Item -Force $next $launcher')
    assert s.index('last-known-good.json') < s.index('Move-Item -Force $next $launcher')

    assert s.index('agentos_ota_rollback=PASS') > s.index('Move-Item -Force $next $launcher')
    assert s.index('agentos_ota_post_switch=PASS') > s.index('agentos_ota_rollback=PASS')

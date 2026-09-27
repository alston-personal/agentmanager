from pathlib import Path
p=Path('scripts/windows/transactional_ota.ps1')
s=p.read_text(encoding='utf-8')
required=['versions','last-known-good.json','candidate_import=PASS','Move-Item -Force $next $launcher','status=\'candidate-validated\'']
def test_contract():
    for marker in required:
        assert marker in s, marker
    assert s.index('candidate_import=PASS') < s.index('Move-Item -Force $next $launcher')
    assert s.index('last-known-good.json') < s.index('Move-Item -Force $next $launcher')

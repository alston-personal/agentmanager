from pathlib import Path

p=Path('scripts/windows/transactional_ota.ps1')
s=p.read_text(encoding='utf-8')

required=[
    'versions',
    'last-known-good.json',
    'candidate_import=PASS',
    'Move-Item -Force $next $launcher',
    'candidate-validated',
    'awaiting-controller-acceptance',
    'agentos_ota_local_health=PASS',
    'agentos_ota_controller_acceptance=PENDING',
    'AgentOS Thin Client OTA Guard',
]

def test_contract():
    for marker in required:
        assert marker in s, marker
    assert s.index('candidate_import=PASS') < s.index('Move-Item -Force $next $launcher')
    assert s.index('last-known-good.json') < s.index('Move-Item -Force $next $launcher')
    assert s.index('awaiting-controller-acceptance') > s.index('Move-Item -Force $next $launcher')
    assert "$record.status='active-accepted'" not in s
    assert "status='active-accepted'" in s  # bootstrap LKG may be accepted

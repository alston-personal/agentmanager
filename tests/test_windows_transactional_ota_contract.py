from pathlib import Path

p=Path('scripts/windows/transactional_ota.ps1')
s=p.read_text(encoding='utf-8')
finalize=Path('scripts/windows/transactional_ota_finalize.ps1').read_text(encoding='utf-8')

required=[
    'versions',
    'last-known-good.json',
    'candidate_import=PASS',
    'Move-Item -Force $next $launcher',
    'candidate-validated',
    'awaiting-controller-acceptance',
    'agentos_ota_controller_acceptance=PENDING',
    'AgentOS Thin Client OTA Guard',
    "Start-Sleep -Seconds 8; Stop-ScheduledTask",
    "Start-ScheduledTask -TaskName '$TaskName'",
    'cannot bootstrap LKG',
    'function Write-JsonAtomic',
]

def test_contract():
    for marker in required:
        assert marker in s, marker
    assert s.index('candidate_import=PASS') < s.index('Write-JsonAtomic $record $currentFile')
    assert s.index('Write-JsonAtomic $record $currentFile') < s.index('Move-Item -Force $next $launcher')
    assert s.index('AgentOS Thin Client OTA Guard') < s.index('Move-Item -Force $next $launcher')
    assert s.index('agentos_ota_controller_acceptance=PENDING') > s.index('Start-Process powershell.exe')
    assert "$record.status='active-accepted'" not in s
    assert "status='active-accepted'" in s  # bootstrap LKG only

def test_finalize_is_atomic_and_supports_new_properties():
    assert 'function Write-JsonAtomic' in finalize
    assert 'Add-Member -NotePropertyName accepted_at' in finalize
    assert 'Add-Member -NotePropertyName rolled_back_at' in finalize
    assert 'Write-JsonAtomic $current $currentFile' in finalize
    assert 'Write-JsonAtomic $lkg $currentFile' in finalize

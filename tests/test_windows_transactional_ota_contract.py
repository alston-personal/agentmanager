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
    'AgentOS Thin Client OTA Activator',
    'transactional_ota_activate-',
    'AGENTOS_RUNTIME_PROVENANCE',
    'cannot bootstrap LKG',
    'function Write-JsonAtomic',
]

def test_contract():
    for marker in required:
        assert marker in s, marker
    assert s.index('candidate_import=PASS') < s.index('Write-JsonAtomic $record $currentFile')
    assert s.index('Write-JsonAtomic $record $currentFile') < s.index('Move-Item -Force $next $launcher')
    assert s.index('AgentOS Thin Client OTA Guard') < s.index('Move-Item -Force $next $launcher')
    assert s.index('agentos_ota_controller_acceptance=PENDING') > s.index('Register-ScheduledTask -TaskName $activatorTask')
    assert "$record.status='active-accepted'" not in s
    assert "status='active-accepted'" in s  # bootstrap LKG only

def test_finalize_is_atomic_and_supports_new_properties():
    assert 'function Write-JsonAtomic' in finalize
    assert 'Add-Member -NotePropertyName accepted_at' in finalize
    assert 'Add-Member -NotePropertyName rolled_back_at' in finalize
    assert 'Write-JsonAtomic $current $currentFile' in finalize
    assert 'Write-JsonAtomic $lkg $currentFile' in finalize

# revalidate current integration head for transactional OTA


def test_script_is_not_concatenated_or_duplicated():
    assert s.count("SourceCommit must be immutable SHA") == 1
    assert s.count("ToolCommit must be immutable SHA") == 1
    assert s.count("AgentOS Thin Client OTA Activator") == 1
    assert s.count("agentos_ota_controller_acceptance=PENDING") == 1
    assert s.count("param([Parameter(Mandatory=$true)][string]$SourceCommit") == 1
    assert len(s.splitlines()) < 400


def test_launchers_are_single_line_assignments():
    assert "('set \"PYTHONPATH={0}\"' -f [string]$candidate)" in s
    assert "('set \"AGENTOS_CLIENT_HOME={0}\"' -f [string]$state)" in s
    assert "('set \"AGENTOS_RUNTIME_PROVENANCE={0}\"' -f [string](Join-Path $candidate 'runtime-provenance.json'))" in s
    assert "candidate launcher validation failed: PYTHONPATH" in s
    assert "candidate launcher validation failed: provenance" in s
    assert "$lines=@('@echo off','set \"PYTHONPATH='+$candidate" not in s
    assert "('set \"PYTHONPATH={0}\"' -f [string]$lkg.path)" in finalize

def test_one_click_supervisor_carrier_follows_current_runtime_state():
    assert "supervisor path could not be resolved from task action" in s
    assert "$current=Get-Content -Raw -LiteralPath $currentFile|ConvertFrom-Json" in s
    assert "$env:PYTHONPATH=$runtime" in s
    assert "$stableSupervisor=Join-Path $InstallRoot 'agentos-thin-client-supervisor.ps1'" in s
    assert "Set-ScheduledTask -TaskName $TaskName -Action $newAction" in s
    assert "Register-ScheduledTask -TaskName $TaskName" not in s
    assert "supervisor_carrier" in s


def test_ota_helpers_are_noninteractive_and_cleaned_up():
    assert "-LogonType S4U" in s
    assert "Register-ScheduledTask -TaskName $guardTask" in s
    assert "Register-ScheduledTask -TaskName $activatorTask" in s
    assert "Remove-OtaHelperTasks" in finalize
    assert "AgentOS Thin Client OTA Guard" in finalize
    assert "AgentOS Thin Client OTA Activator" in finalize


def test_rollback_publishes_lkg_before_supervisor_restart():
    write_idx = finalize.index("Write-JsonAtomic $lkg $currentFile 8")
    stop_idx = finalize.index("Stop-ScheduledTask -TaskName $TaskName")
    start_idx = finalize.index("Start-ScheduledTask -TaskName $TaskName")
    assert write_idx < stop_idx < start_idx


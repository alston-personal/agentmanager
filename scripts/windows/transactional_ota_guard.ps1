param([string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",[string]$TaskName='AgentOS Thin Client')
$ErrorActionPreference='Stop'
$currentFile=Join-Path $InstallRoot 'current.json'
if(-not(Test-Path $currentFile)){exit 0}
$current=Get-Content -Raw $currentFile|ConvertFrom-Json
if($current.status -ne 'awaiting-controller-acceptance'){exit 0}
if(-not $current.rollback_deadline){throw 'pending OTA has no rollback deadline'}
$deadline=[DateTimeOffset]::Parse([string]$current.rollback_deadline)
if([DateTimeOffset]::UtcNow -lt $deadline){exit 0}
$helper=[string]$current.finalize_helper
if(-not $helper){$helper=Join-Path $InstallRoot 'transactional_ota_finalize.ps1'}
if(-not(Test-Path $helper)){throw 'OTA rollback helper missing'}
& $helper -Action rollback -InstallRoot $InstallRoot -TaskName $TaskName
Write-Output 'agentos_ota_deadline_rollback=PASS'

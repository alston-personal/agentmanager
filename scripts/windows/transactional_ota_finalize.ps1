param([Parameter(Mandatory=$true)][ValidateSet('accept','rollback')][string]$Action,[string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",[string]$TaskName='AgentOS Thin Client')
$ErrorActionPreference='Stop'
$currentFile=Join-Path $InstallRoot 'current.json'
$lkgFile=Join-Path $InstallRoot 'last-known-good.json'
$launcher=Join-Path $InstallRoot 'agentos-client.cmd'
$state=Join-Path $InstallRoot 'state'
if(-not(Test-Path $currentFile)){throw 'current runtime record missing'}
$current=Get-Content -Raw $currentFile|ConvertFrom-Json
if($Action -eq 'accept'){
  if($current.status -ne 'awaiting-controller-acceptance'){throw 'runtime is not awaiting acceptance'}
  $current.status='active-accepted'
  $current.accepted_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  $current|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 $currentFile
  $current|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 $lkgFile
  Write-Output 'agentos_ota_finalize=PASS'
  exit 0
}
if(-not(Test-Path $lkgFile)){throw 'last-known-good runtime missing'}
$lkg=Get-Content -Raw $lkgFile|ConvertFrom-Json
if(-not $lkg.path){throw 'last-known-good path missing'}
$next=Join-Path $InstallRoot 'agentos-client.rollback.cmd'
@('@echo off','set "PYTHONPATH='+[string]$lkg.path+'"','set "AGENTOS_CLIENT_HOME='+$state+'"','python -m agentos_node.client_cli %*')|Set-Content -Encoding ASCII $next
Move-Item -Force $next $launcher
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $TaskName
$lkg.status='rollback-restored'
$lkg.rolled_back_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$lkg|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 $currentFile
Write-Output 'agentos_ota_rollback=PASS'

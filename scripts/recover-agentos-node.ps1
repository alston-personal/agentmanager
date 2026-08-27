param(
  [string]$Ref = 'main',
  [switch]$SkipVerify
)

$ErrorActionPreference = 'Stop'
$install = Join-Path $env:LOCALAPPDATA 'AgentOS'
$pkg = Join-Path $install 'agentos_node'
$base = "https://raw.githubusercontent.com/alston-personal/agentmanager/$Ref"
$files = @(
  'agentos_node/thin_client.py',
  'agentos_node/interactive_desktop.py',
  'agentos_node/thin_client_transport.py',
  'agentos_node/client_cli.py',
  'agentos_node/agent_surfaces.py',
  'agentos_node/session_bridge.py',
  'agentos_node/onboarding.py'
)

New-Item -ItemType Directory -Force -Path $pkg | Out-Null
foreach ($rel in $files) {
  $dest = Join-Path $install ($rel -replace '/', '\')
  $parent = Split-Path -Parent $dest
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri "$base/$rel" -OutFile $dest
}

$launcher = Join-Path $install 'agentos-client.cmd'
if (-not (Test-Path $launcher)) {
  $python = (Get-Command python -ErrorAction Stop).Source
  $launcherText = "@echo off`r`nset PYTHONPATH=$install`r`n`"$python`" -m agentos_node.client_cli %*`r`n"
  Set-Content -Path $launcher -Value $launcherText -Encoding ASCII
}

$config = Join-Path $env:USERPROFILE '.agentos\client.json'
$policy = Join-Path $env:USERPROFILE '.agentos\policy.json'
if (-not (Test-Path $config)) { throw "Existing Node config not found: $config" }
if (-not (Test-Path $policy)) { throw "Existing Node policy not found: $policy" }

$taskName = 'AgentOS Thin Client'
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/d /c `"$launcher`" run" -WorkingDirectory $install
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'AgentOS Thin Client user-session daemon' -Force | Out-Null
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3

$health = & $launcher health 2>&1
Write-Host $health
if ($LASTEXITCODE -ne 0) { throw 'AgentOS ONE health check failed after recovery' }

$manifest = & $launcher manifest 2>&1
Write-Host $manifest
if ($LASTEXITCODE -ne 0) { throw 'AgentOS manifest discovery failed after recovery' }

if (-not $SkipVerify) {
  $verify = & $launcher verify 2>&1
  Write-Host $verify
  if ($LASTEXITCODE -ne 0) { throw 'AgentOS readiness verification failed after recovery' }
}

Write-Host 'agentos_node_recovery=PASS'
Write-Host "agentos_runtime_ref=$Ref"

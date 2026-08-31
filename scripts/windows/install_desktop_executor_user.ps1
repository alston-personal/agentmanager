param(
  [string]$TaskName = 'AgentOS Desktop Executor',
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$BridgeRoot = "$env:ProgramData\AgentOS\executor-bridges\desktop-$env:USERNAME"
)

$ErrorActionPreference = 'Stop'

$required = @(
  'agentos_node\desktop_executor_cli.py',
  'agentos_node\desktop_executor_host.py',
  'agentos_node\executor_bridge.py',
  'agentos_node\executor_registry.py',
  'agentos_node\interactive_desktop.py',
  'agentos_node\thin_client.py'
)
foreach ($rel in $required) {
  $path = Join-Path $InstallRoot $rel
  if (-not (Test-Path $path)) { throw "Missing desktop executor runtime file: $path" }
}
if (-not (Test-Path $BridgeRoot)) {
  throw "Desktop executor bridge does not exist: $BridgeRoot. Install the AgentOS Node Runtime service first."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python 3 is required for the AgentOS Desktop Executor.' }

$launcherPath = Join-Path $InstallRoot 'agentos-desktop-executor.cmd'
$launcher = @"
@echo off
set "PYTHONPATH=$InstallRoot"
"$($python.Source)" -m agentos_node.desktop_executor_cli %*
"@
$launcher | Set-Content -Encoding ASCII $launcherPath

$action = New-ScheduledTaskAction `
  -Execute 'cmd.exe' `
  -Argument "/d /c `"$launcherPath`" --bridge `"$BridgeRoot`" run" `
  -WorkingDirectory $InstallRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 10 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal `
  -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Description 'AgentOS interactive desktop executor host; no Realm transport credential' `
  -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 1
$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "Desktop executor task: $TaskName"
Write-Host "Task state: $($task.State)"
Write-Host "Bridge: $BridgeRoot"
Write-Host 'This task hosts desktop capabilities only; it does not own the AgentOS Realm transport.'

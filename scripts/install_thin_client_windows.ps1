param(
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$WorkspaceRoot = "$HOME\AgentOS",
  [switch]$EnableAutostart
)

$ErrorActionPreference = 'Stop'
$Repo = 'alston-personal/agentmanager'
$apiHeaders = @{
  'Accept' = 'application/vnd.github+json'
  'User-Agent' = 'AgentOS-ThinClient-Installer/0.1'
  'Cache-Control' = 'no-cache'
}
$head = Invoke-RestMethod -UseBasicParsing -Headers $apiHeaders -Uri "https://api.github.com/repos/$Repo/commits/main?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$Ref = [string]$head.sha
if ($Ref -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve immutable main commit SHA: $Ref" }
$Base = "https://raw.githubusercontent.com/$Repo/$Ref"
$Pkg = Join-Path $InstallRoot 'agentos_node'
$State = Join-Path $InstallRoot 'state'
New-Item -ItemType Directory -Force -Path $Pkg, $State, $WorkspaceRoot | Out-Null

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw 'Python 3 is required for Thin Client v0.1. Install Python 3 and ensure python.exe is on PATH.'
}
$version = & $python.Source -c "import sys; print('.'.join(map(str,sys.version_info[:3])))"
$major = [int]($version.Split('.')[0])
if ($major -lt 3) { throw "Python 3 is required; found $version" }

$files = @(
  'agentos_node/__init__.py',
  'agentos_node/thin_client.py',
  'agentos_node/thin_client_transport.py',
  'agentos_node/client_cli.py'
)
foreach ($rel in $files) {
  $dest = Join-Path $InstallRoot ($rel -replace '/', '\')
  New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
  Invoke-WebRequest -UseBasicParsing -Headers @{ 'Cache-Control'='no-cache' } -Uri "$Base/$rel" -OutFile $dest
}

$clientCli = Join-Path $Pkg 'client_cli.py'
$clientCliText = Get-Content -Raw $clientCli
if ($clientCliText -notmatch "encoding='utf-8-sig'") {
  throw "Downloaded client_cli.py failed BOM-compatibility guard (ref=$Ref)"
}

$policy = @{
  schema = 'agentos.client-policy/v0.1'
  allowed_executables = @('git','python','python.exe','python3','powershell','powershell.exe','pwsh','cmd','cmd.exe')
  readable_roots = @((Resolve-Path $WorkspaceRoot).Path)
  writable_roots = @((Resolve-Path $WorkspaceRoot).Path)
  max_timeout_seconds = 120
} | ConvertTo-Json -Depth 5
$policy | Set-Content -Encoding UTF8 (Join-Path $State 'policy.json')

$launcher = @"
@echo off
set "PYTHONPATH=$InstallRoot"
set "AGENTOS_CLIENT_HOME=$State"
"$($python.Source)" -m agentos_node.client_cli %*
"@
$launcherPath = Join-Path $InstallRoot 'agentos-client.cmd'
$launcher | Set-Content -Encoding ASCII $launcherPath

if ($EnableAutostart) {
  if (-not (Test-Path (Join-Path $State 'client.json'))) {
    throw 'Client is not enrolled yet. Run agentos-client.cmd join first, then rerun installer with -EnableAutostart.'
  }
  $taskName = 'AgentOS Thin Client'
  $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/d /c `"$launcherPath`" run" -WorkingDirectory $InstallRoot
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'AgentOS Thin Client user-session daemon' -Force | Out-Null
  Start-ScheduledTask -TaskName $taskName
  Write-Host "Autostart enabled: $taskName"
}

Write-Host "AgentOS Thin Client installed: $InstallRoot"
Write-Host "Source commit: $Ref"
Write-Host "Python: $version"
Write-Host "Policy workspace: $WorkspaceRoot"
Write-Host "Launcher: $launcherPath"
Write-Host ''
Write-Host 'Next command:'
Write-Host "  & '$launcherPath' join --one https://studio.milkcat.org/dashboard/api/agentos"

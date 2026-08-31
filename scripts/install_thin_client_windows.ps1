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
  'agentos_node/agent_surfaces.py',
  'agentos_node/client_cli.py',
  'agentos_node/desktop_executor_cli.py',
  'agentos_node/desktop_executor_host.py',
  'agentos_node/executor_bridge.py',
  'agentos_node/executor_registry.py',
  'agentos_node/interactive_desktop.py',
  'agentos_node/onboarding.py',
  'agentos_node/session_bridge.py',
  'agentos_node/thin_client.py',
  'agentos_node/thin_client_transport.py'
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
foreach ($required in @('interactive_desktop.py','executor_bridge.py','executor_registry.py','desktop_executor_host.py','desktop_executor_cli.py')) {
  if (-not (Test-Path (Join-Path $Pkg $required))) {
    throw "Required AgentOS runtime module missing: $required (ref=$Ref)"
  }
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
  throw @'
-EnableAutostart no longer installs the combined interactive Thin Client task.
AgentOS now separates the always-on Node Runtime from user-session executors.
Install the Node Runtime Windows Service with scripts/windows/install_node_runtime_service.ps1,
then install the interactive desktop executor with scripts/windows/install_desktop_executor_user.ps1.
'@
}

Write-Host "AgentOS Thin Client runtime installed: $InstallRoot"
Write-Host "Source commit: $Ref"
Write-Host "Python: $version"
Write-Host "Policy workspace: $WorkspaceRoot"
Write-Host "Launcher: $launcherPath"
Write-Host "Executor bridge runtime: installed"
Write-Host ''
Write-Host 'Next command for a new node:'
Write-Host "  & '$launcherPath' join --one https://studio.milkcat.org/dashboard/api/agentos"
Write-Host 'After enrollment, install the split Node Service and user-session Desktop Executor carriers.'

param(
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$WorkspaceRoot = "$HOME\AgentOS",
  [string]$SourceRef = "main",
  [string]$PythonExe = ""
)

$ErrorActionPreference = 'Stop'
$Repo = 'alston-personal/agentmanager'
$apiHeaders = @{
  'Accept' = 'application/vnd.github+json'
  'User-Agent' = 'AgentOS-ThinClient-Installer/1.0'
  'Cache-Control' = 'no-cache'
}

function Test-RealPython([string]$Candidate) {
  if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
  if (-not (Test-Path -LiteralPath $Candidate)) { return $null }
  try {
    $output = @(& $Candidate -c "import sys; print('.'.join(map(str,sys.version_info[:3])))" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $output.Count -eq 0) { return $null }
    $versionText = ([string]$output[-1]).Trim()
    if ($versionText -notmatch '^(?<major>[0-9]+)\.[0-9]+\.[0-9]+$') { return $null }
    if ([int]$Matches.major -lt 3) { return $null }
    return @{ Path = (Resolve-Path -LiteralPath $Candidate).Path; Version = $versionText }
  } catch {
    return $null
  }
}

function Resolve-RealPython([string]$Explicit) {
  if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
    $validated = Test-RealPython $Explicit
    if ($validated) { return $validated }
    throw "Explicit PythonExe is not a working Python 3 interpreter: $Explicit"
  }

  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($name in @('python','python3')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { $candidates.Add([string]$cmd.Source) }
  }
  foreach ($pattern in @(
    "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
    "$env:ProgramFiles\Python3*\python.exe"
  )) {
    Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending |
      ForEach-Object { $candidates.Add($_.FullName) }
  }
  foreach ($candidate in ($candidates | Select-Object -Unique)) {
    $validated = Test-RealPython $candidate
    if ($validated) { return $validated }
  }
  throw 'A real Python 3 interpreter was not found. Windows Store App Execution Alias is not accepted.'
}

$encodedRef = [uri]::EscapeDataString($SourceRef)
$head = Invoke-RestMethod -UseBasicParsing -Headers $apiHeaders -Uri "https://api.github.com/repos/$Repo/commits/${encodedRef}?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$Ref = [string]$head.sha
if ($Ref -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve immutable source commit SHA: $Ref" }
$Base = "https://raw.githubusercontent.com/$Repo/$Ref"

$Pkg = Join-Path $InstallRoot 'agentos_node'
$State = Join-Path $InstallRoot 'state'
New-Item -ItemType Directory -Force -Path $Pkg, $State, $WorkspaceRoot | Out-Null

$pythonInfo = Resolve-RealPython $PythonExe
$pythonPath = [string]$pythonInfo.Path
$version = [string]$pythonInfo.Version

$files = @(
  'agentos_node/__init__.py',
  'agentos_node/thin_client.py',
  'agentos_node/interactive_desktop.py',
  'agentos_node/thin_client_transport.py',
  'agentos_node/client_cli.py',
  'agentos_node/session_bridge.py',
  'agentos_node/agent_surfaces.py'
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
foreach ($required in @('thin_client.py','interactive_desktop.py','thin_client_transport.py','session_bridge.py','agent_surfaces.py')) {
  if (-not (Test-Path (Join-Path $Pkg $required))) {
    throw "Thin Client dependency missing: $required (ref=$Ref)"
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
"$pythonPath" -m agentos_node.client_cli %*
"@
$launcherPath = Join-Path $InstallRoot 'agentos-client.cmd'
$launcher | Set-Content -Encoding ASCII $launcherPath

Write-Host "AgentOS Thin Client files installed: $InstallRoot"
Write-Host "Source commit: $Ref"
Write-Host "Python: $version"
Write-Host "Policy workspace: $WorkspaceRoot"
Write-Host "Launcher: $launcherPath"

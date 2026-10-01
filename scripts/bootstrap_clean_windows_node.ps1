param(
  [string]$NodeId = "",
  [string]$OneUrl = "https://studio.milkcat.org/dashboard/api/agentos",
  [string]$SourceRef = "core/integration",
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$WorkspaceRoot = "$HOME\AgentOS"
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ([string]::IsNullOrWhiteSpace($NodeId)) { $NodeId = $env:COMPUTERNAME.ToLowerInvariant() }
if ($NodeId -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw "Invalid NodeId: $NodeId" }

function Resolve-Python {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) {
    try {
      $major = & $cmd.Source -c "import sys; print(sys.version_info.major)"
      if ([int]$major -ge 3) { return $cmd.Source }
    } catch {}
  }
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) { throw "Python 3 is required and winget is unavailable. Install Python 3, then rerun this bootstrap." }
  Write-Host "agentos_bootstrap_python=INSTALLING"
  & $winget.Source install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements --silent
  if ($LASTEXITCODE -ne 0) { throw "Python installation failed with exit code $LASTEXITCODE" }
  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      try {
        $probe = @(& $candidate -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $probe.Count -gt 0) { return $candidate }
      } catch {}
    }
  }
  throw "Python was installed but a real python.exe could not be resolved in this session."
}

$python = Resolve-Python
Write-Host "agentos_bootstrap_python=$python"

$repo = 'alston-personal/agentmanager'
$headers = @{ 'Accept'='application/vnd.github+json'; 'User-Agent'='AgentOS-Clean-Windows-Bootstrap/0.1'; 'Cache-Control'='no-cache' }
$encodedRef = [uri]::EscapeDataString($SourceRef)
$commit = Invoke-RestMethod -UseBasicParsing -Headers $headers -Uri "https://api.github.com/repos/$repo/commits/$encodedRef"
$sha = [string]$commit.sha
if ($sha -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve immutable source commit for $SourceRef" }

$tempInstaller = Join-Path $env:TEMP "agentos-install-thin-client-$($sha.Substring(0,12)).ps1"
$installerUrl = "https://raw.githubusercontent.com/$repo/$sha/scripts/install_thin_client_windows.ps1"
Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri $installerUrl -OutFile $tempInstaller
Write-Host "agentos_bootstrap_source_commit=$sha"
Write-Host "agentos_bootstrap_installer=$tempInstaller"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tempInstaller -InstallRoot $InstallRoot -WorkspaceRoot $WorkspaceRoot -SourceRef $sha -PythonExe $python
if ($LASTEXITCODE -ne 0) { throw "Thin Client installer failed with exit code $LASTEXITCODE" }

$launcher = Join-Path $InstallRoot 'agentos-client.cmd'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Thin Client launcher missing after install: $launcher" }
$state = Join-Path $InstallRoot 'state'
$config = Join-Path $state 'client.json'
$policy = Join-Path $state 'policy.json'
if (-not (Test-Path -LiteralPath $policy)) { throw "Thin Client policy missing after install: $policy" }

if (-not (Test-Path -LiteralPath $config)) {
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " AgentOS enrollment will now start."
  Write-Host " Keep this PowerShell window open."
  Write-Host " When a Code appears, send that Code to your AgentOS admin."
  Write-Host "============================================================"
  Write-Host ""
  & $launcher join --one $OneUrl --node-id $NodeId --timeout-seconds 900
  if ($LASTEXITCODE -ne 0) { throw "AgentOS enrollment/join failed with exit code $LASTEXITCODE" }
} else {
  Write-Host "agentos_bootstrap_enrollment=EXISTING"
}

# Converge lifecycle even on resume after a partially completed join.
$oldPythonPath = $env:PYTHONPATH
$oldClientHome = $env:AGENTOS_CLIENT_HOME
try {
  $env:PYTHONPATH = $InstallRoot
  $env:AGENTOS_CLIENT_HOME = $state
  & $python -c "import json; from agentos_node.onboarding import install_node_supervisor; r=install_node_supervisor(); print(json.dumps(r, ensure_ascii=False)); raise SystemExit(0 if r.get('supervisor_ready') else 2)"
  if ($LASTEXITCODE -ne 0) { throw "AgentOS lifecycle supervisor convergence failed" }
  Write-Host "agentos_bootstrap_supervisor=PASS"
} finally {
  $env:PYTHONPATH = $oldPythonPath
  $env:AGENTOS_CLIENT_HOME = $oldClientHome
}

& $launcher health
if ($LASTEXITCODE -ne 0) { throw "AgentOS health check failed" }
& $launcher manifest
if ($LASTEXITCODE -ne 0) { throw "AgentOS manifest check failed" }
& $launcher verify
if ($LASTEXITCODE -ne 0) { throw "AgentOS readiness verification failed" }

Write-Host ""
Write-Host "agentos_clean_windows_node=PASS"
Write-Host "agentos_node_id=$NodeId"
Write-Host "agentos_one_url=$OneUrl"
Write-Host "agentos_source_commit=$sha"

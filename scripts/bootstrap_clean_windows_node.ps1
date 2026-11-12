param(
  [string]$NodeId = "",
  [string]$OneUrl = "https://studio.milkcat.org/dashboard/api/agentos",
  [string]$RealmId = "",
  [string]$SourceRef = "core/integration",
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$WorkspaceRoot = "$HOME\AgentOS",
  [switch]$SwitchRealm
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ([string]::IsNullOrWhiteSpace($NodeId)) { $NodeId = $env:COMPUTERNAME.ToLowerInvariant() }
if ($NodeId -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw "Invalid NodeId: $NodeId" }

if (-not [string]::IsNullOrWhiteSpace($RealmId)) {
  if ($RealmId -notmatch '^realm-u-[0-9a-f]{24}$') { throw 'Invalid tenant RealmId' }
  if ($OneUrl -eq 'https://studio.milkcat.org/dashboard/api/agentos') {
    $OneUrl = 'https://agentos.milkcat.org'
  }
  if ($SourceRef -eq 'core/integration') { $SourceRef = 'main' }
  if ($OneUrl -ne 'https://agentos.milkcat.org') { throw 'Tenant onboarding requires the AgentOS public origin' }
}
$OneUrl = $OneUrl.TrimEnd('/')

$parsedOne = $null
if (-not [uri]::TryCreate($OneUrl, [System.UriKind]::Absolute, [ref]$parsedOne) -or $parsedOne.Scheme -ne 'https') {
  throw "OneUrl must be an absolute HTTPS URL: $OneUrl"
}

function Test-WorkingPython([string]$Candidate) {
  if ([string]::IsNullOrWhiteSpace($Candidate) -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
  try {
    # Never allow Store/winget banners or application-alias text to become a path.
    $probe = @(& $Candidate -c "import sys; assert sys.version_info.major >= 3" 2>$null)
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

function Resolve-Python {
  # The Windows Store app-execution alias is not a working Python interpreter.
  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($candidate in @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
  )) { $candidates.Add($candidate) }
  foreach ($cmdName in @('python','python3')) {
    $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { $candidates.Add([string]$cmd.Source) }
  }
  foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (Test-WorkingPython $candidate) { return $candidate }
  }
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) { throw 'Python 3 is required and winget is unavailable. Install Python 3, then rerun this bootstrap.' }
  Write-Host 'agentos_bootstrap_python=INSTALLING'
  # Explicitly discard installer output: only a validated path may be returned.
  & $winget.Source install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements --silent | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Python installation failed with exit code $LASTEXITCODE" }
  foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (Test-WorkingPython $candidate) { return $candidate }
  }
  throw 'Python installation completed, but no working Python 3 executable was found at the expected user install paths.'
}

# Preflight active binding before downloading/installing anything. A cross-Realm
# request cannot overwrite an active Thin Client as a side effect of onboarding.
$activeRoot = $InstallRoot
$originalConfig = Join-Path (Join-Path $InstallRoot 'state') 'client.json'
$originalPolicy = Join-Path (Join-Path $InstallRoot 'state') 'policy.json'
$stagingRebind = $false
if (Test-Path -LiteralPath $originalConfig) {
  try {
    $currentBinding = Get-Content -Raw -LiteralPath $originalConfig | ConvertFrom-Json
    $boundOne = ([string]$currentBinding.one_url).TrimEnd('/')
    $boundRealm = [string]$currentBinding.realm_id
    $boundNode = [string]$currentBinding.node_id
    if ([string]::IsNullOrWhiteSpace($boundRealm) -or [string]::IsNullOrWhiteSpace($boundNode)) { throw 'invalid existing binding' }
  } catch {
    throw 'Active Node config cannot be read; refusing to replace its enrollment.'
  }
  $targetDifferent = ($boundOne -ne $OneUrl) -or (
    -not [string]::IsNullOrWhiteSpace($RealmId) -and $boundRealm -ne $RealmId)
  if ($targetDifferent) {
    if (-not $SwitchRealm) {
      throw 'Existing Node targets a different Realm. Add -SwitchRealm to stage a new binding without altering the active one.'
    }
    if ($NodeId -ne $boundNode) {
      throw 'Staged rebind must preserve the existing Node identity; use the original NodeId.'
    }
    $stagingRebind = $true
    $activeRoot = Join-Path $env:LOCALAPPDATA ('AgentOS-realm-stage-' + [guid]::NewGuid().ToString('N'))
    # Staging requires the current protected-main client with --stage-only.
    $SourceRef = 'main'
    Write-Host 'agentos_realm_switch=STAGING'
    Write-Host "agentos_existing_realm=$boundRealm"
    Write-Host "agentos_target_realm=$RealmId"
  }
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

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tempInstaller -InstallRoot $activeRoot -WorkspaceRoot $WorkspaceRoot -SourceRef $sha -PythonExe $python
if ($LASTEXITCODE -ne 0) { throw "Thin Client installer failed with exit code $LASTEXITCODE" }

$launcher = Join-Path $activeRoot 'agentos-client.cmd'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Thin Client launcher missing after install: $launcher" }
$state = Join-Path $activeRoot 'state'
$config = Join-Path $state 'client.json'
$policy = Join-Path $state 'policy.json'
if (-not (Test-Path -LiteralPath $policy)) { throw "Thin Client policy missing after install: $policy" }

if ($stagingRebind) {
  if (Test-Path -LiteralPath $originalPolicy) {
    # Preserve original policy exactly for a staged client; the source policy is untouched.
    Copy-Item -LiteralPath $originalPolicy -Destination $policy -Force
  }
  $stagedConfig = Join-Path $state 'client.stage.json'
  $stageArgs = @("--config", $stagedConfig, "join", "--one", $OneUrl, "--node-id", $NodeId,
                 "--timeout-seconds", "900", "--stage-only")
  if (-not [string]::IsNullOrWhiteSpace($RealmId)) { $stageArgs += @("--realm-id", $RealmId) }
  & $launcher @stageArgs
  if ($LASTEXITCODE -ne 0) {
    throw 'Target Realm claim/heartbeat failed; the original Node config remains active.'
  }
  if (-not (Test-Path -LiteralPath $stagedConfig)) { throw 'Target Node claim did not write staged config.' }
  $staged = Get-Content -Raw -LiteralPath $stagedConfig | ConvertFrom-Json
  if (([string]$staged.one_url).TrimEnd('/') -ne $OneUrl -or
      [string]$staged.node_id -ne $boundNode -or
      (-not [string]::IsNullOrWhiteSpace($RealmId) -and [string]$staged.realm_id -ne $RealmId)) {
    throw 'Staged binding identity mismatch; original Node config remains active.'
  }
  Write-Host 'agentos_realm_switch=STAGED_VERIFIED'
  Write-Host "agentos_stage_root=$activeRoot"
  Write-Host 'agentos_active_binding=PRESERVED'
  Write-Host 'agentos_realm_switch_cutover=NOT_AUTHORIZED_UNTIL_SUPERVISOR_ROLLBACK_VERIFIED'
  exit 0
}


$needsEnrollment = -not (Test-Path -LiteralPath $config)
if (-not $needsEnrollment) {
  try {
    $existing = Get-Content -Raw -LiteralPath $config | ConvertFrom-Json
    $existingOne = ([string]$existing.one_url).TrimEnd('/')
    $existingRealm = [string]$existing.realm_id
  } catch {
    throw "Existing AgentOS client config is unreadable: $config"
  }
  if ($existingOne -ne $OneUrl -or (-not [string]::IsNullOrWhiteSpace($RealmId) -and $existingRealm -ne $RealmId)) {
    Write-Host "agentos_existing_realm=$existingRealm"
    Write-Host "agentos_existing_one_url=$existingOne"
    Write-Host "agentos_requested_one_url=$OneUrl"
    throw 'Unexpected Realm mismatch after preflight; refusing to change active Node configuration.'
  } else {
    Write-Host "agentos_bootstrap_enrollment=EXISTING"
    Write-Host "agentos_existing_realm=$existingRealm"
  }
}

if ($needsEnrollment) {
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " AgentOS enrollment will now start."
  Write-Host " Target ONE: $OneUrl"
  Write-Host " Keep this PowerShell window open."
  Write-Host " When a Code appears, send that Code to the target Realm admin."
  Write-Host "============================================================"
  Write-Host ""
  $joinArgs = @("join", "--one", $OneUrl, "--node-id", $NodeId, "--timeout-seconds", "900")
  if (-not [string]::IsNullOrWhiteSpace($RealmId)) { $joinArgs += @("--realm-id", $RealmId) }
  & $launcher @joinArgs
  if ($LASTEXITCODE -ne 0) { throw "AgentOS enrollment/join failed with exit code $LASTEXITCODE" }
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
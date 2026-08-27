param(
  [string]$SourceRef = 'feature/node-executor-runtime',
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$LegacyTaskName = 'AgentOS Thin Client',
  [string]$NodeServiceName = 'AgentOSNodeRuntime',
  [string]$DesktopTaskName = 'AgentOS Desktop Executor'
)

$ErrorActionPreference = 'Stop'
$Repo = 'alston-personal/agentmanager'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Run this migration from an elevated PowerShell window (Run as administrator).'
}

$launcher = Join-Path $InstallRoot 'agentos-client.cmd'
$stateRoot = Join-Path $InstallRoot 'state'
if (-not (Test-Path $launcher)) { throw "Existing AgentOS launcher not found: $launcher" }
if (-not (Test-Path (Join-Path $stateRoot 'client.json'))) { throw 'Existing node enrollment is required; client.json was not found.' }
if (-not (Test-Path (Join-Path $stateRoot 'policy.json'))) { throw 'Existing node policy is required; policy.json was not found.' }

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $InstallRoot "migration-backup-$timestamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
if (Test-Path (Join-Path $InstallRoot 'agentos_node')) {
  Copy-Item -Recurse -Force (Join-Path $InstallRoot 'agentos_node') (Join-Path $backupRoot 'agentos_node')
}
Copy-Item -Force $launcher (Join-Path $backupRoot 'agentos-client.cmd')

$legacyTask = Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue
$legacyWasEnabled = $false
$legacyWasRunning = $false
if ($legacyTask) {
  $legacyWasEnabled = ($legacyTask.State -ne 'Disabled')
  $legacyWasRunning = ($legacyTask.State -eq 'Running')
}

function Restore-LegacyRuntime {
  Write-Warning 'Migration failed; restoring prior AgentOS runtime.'
  Stop-Service -Name $NodeServiceName -Force -ErrorAction SilentlyContinue
  & sc.exe delete $NodeServiceName 2>$null | Out-Null
  Unregister-ScheduledTask -TaskName $DesktopTaskName -Confirm:$false -ErrorAction SilentlyContinue

  $currentPkg = Join-Path $InstallRoot 'agentos_node'
  if (Test-Path $currentPkg) { Remove-Item -Recurse -Force $currentPkg }
  $backupPkg = Join-Path $backupRoot 'agentos_node'
  if (Test-Path $backupPkg) { Copy-Item -Recurse -Force $backupPkg $currentPkg }
  Copy-Item -Force (Join-Path $backupRoot 'agentos-client.cmd') $launcher

  if ($legacyTask) {
    if ($legacyWasEnabled) { Enable-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue | Out-Null }
    if ($legacyWasRunning -or $legacyWasEnabled) { Start-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue }
  }
}

try {
  $headers = @{
    'Accept' = 'application/vnd.github+json'
    'User-Agent' = 'AgentOS-NodeRuntime-Migration/0.1'
    'Cache-Control' = 'no-cache'
  }
  $encodedRef = [uri]::EscapeDataString($SourceRef)
  $head = Invoke-RestMethod -UseBasicParsing -Headers $headers -Uri "https://api.github.com/repos/$Repo/commits/$encodedRef?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
  $Ref = [string]$head.sha
  if ($Ref -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve immutable source commit: $SourceRef" }
  $Base = "https://raw.githubusercontent.com/$Repo/$Ref"

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

  $serviceInstaller = Join-Path $InstallRoot 'install_node_runtime_service.ps1'
  $desktopInstaller = Join-Path $InstallRoot 'install_desktop_executor_user.ps1'
  Invoke-WebRequest -UseBasicParsing -Headers @{ 'Cache-Control'='no-cache' } -Uri "$Base/scripts/windows/install_node_runtime_service.ps1" -OutFile $serviceInstaller
  Invoke-WebRequest -UseBasicParsing -Headers @{ 'Cache-Control'='no-cache' } -Uri "$Base/scripts/windows/install_desktop_executor_user.ps1" -OutFile $desktopInstaller

  # Local import/manifest preflight before changing any carrier.
  $manifestOutput = & $launcher manifest 2>&1
  if ($LASTEXITCODE -ne 0) { throw "Updated runtime manifest preflight failed: $manifestOutput" }
  $manifestText = ($manifestOutput | Out-String)
  if ($manifestText -notmatch '"executors"') { throw 'Updated runtime manifest does not expose executor inventory.' }
  if ($manifestText -notmatch '"executor.inspect"') { throw 'Updated runtime manifest is missing executor.inspect.' }
  Write-Host "runtime_preflight=PASS ref=$Ref"

  & $serviceInstaller -ServiceName $NodeServiceName -InstallRoot $InstallRoot -LegacyTaskName $LegacyTaskName
  if ($LASTEXITCODE -ne 0) { throw 'Node Runtime Service installer returned a non-zero exit code.' }

  $service = Get-Service -Name $NodeServiceName -ErrorAction Stop
  $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
  if ($service.Status -ne 'Running') { throw 'Node Runtime Service did not remain Running.' }
  Write-Host 'node_service=PASS'

  & $desktopInstaller -TaskName $DesktopTaskName -InstallRoot $InstallRoot
  if ($LASTEXITCODE -ne 0) { throw 'Desktop Executor installer returned a non-zero exit code.' }

  Start-Sleep -Seconds 2
  $desktopTask = Get-ScheduledTask -TaskName $DesktopTaskName -ErrorAction Stop
  if ($desktopTask.State -notin @('Running','Ready')) { throw "Unexpected Desktop Executor task state: $($desktopTask.State)" }
  Write-Host "desktop_executor_task=PASS state=$($desktopTask.State)"

  $result = [ordered]@{
    schema = 'agentos.windows-node-migration/v0.1'
    ok = $true
    source_ref = $SourceRef
    source_commit = $Ref
    node_service = $NodeServiceName
    node_service_status = $service.Status.ToString()
    desktop_task = $DesktopTaskName
    desktop_task_status = $desktopTask.State.ToString()
    legacy_task_retained = [bool]$legacyTask
    backup_root = $backupRoot
    credential_values_printed = $false
  }
  $result | ConvertTo-Json -Depth 5
}
catch {
  Restore-LegacyRuntime
  throw
}

param(
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$WorkspaceRoot = "$HOME\AgentOS",
  [string]$SourceRef = "main",
  [string]$PythonExe = "",
  [switch]$EnableAutostart
)

$ErrorActionPreference = 'Stop'
$Repo = 'alston-personal/agentmanager'
$apiHeaders = @{
  'Accept' = 'application/vnd.github+json'
  'User-Agent' = 'AgentOS-ThinClient-Installer/1.0'
  'Cache-Control' = 'no-cache'
}
$encodedRef = [uri]::EscapeDataString($SourceRef)
$head = Invoke-RestMethod -UseBasicParsing -Headers $apiHeaders -Uri "https://api.github.com/repos/$Repo/commits/${encodedRef}?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$Ref = [string]$head.sha
if ($Ref -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve immutable main commit SHA: $Ref" }
$Base = "https://raw.githubusercontent.com/$Repo/$Ref"

$Pkg = Join-Path $InstallRoot 'agentos_node'
$State = if([string]::IsNullOrWhiteSpace($StateRoot)){ Join-Path $InstallRoot 'state' } else { $StateRoot }
New-Item -ItemType Directory -Force -Path $Pkg, $State, $WorkspaceRoot | Out-Null

  'agentos_node/client_cli.py',
  'agentos_node/session_bridge.py',
  'agentos_node/agent_surfaces.py',
  'agentos_node/employee_wake_inbox.py',
  'agentos_node/runtime_provenance.py'
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
foreach ($required in @('thin_client.py','interactive_desktop.py','semantic_preview.py','desktop_plan.py','thin_client_transport.py','session_bridge.py','agent_surfaces.py')) {
  if (-not (Test-Path (Join-Path $Pkg $required))) {
    throw "Thin Client dependency missing: $required (ref=$Ref)"
  }
}
foreach ($required in @('node_adapter.py','session_bridge.py','agent_surfaces.py','employee_wake_inbox.py','runtime_provenance.py')) {
  if (-not (Test-Path (Join-Path $Pkg $required))) {
    throw "Thin Client dependency missing: $required (ref=$Ref)"
  }
}

$policyPath = Join-Path $State 'policy.json'
if (-not (Test-Path -LiteralPath $policyPath)) {
  $policy = @{
    schema = 'agentos.client-policy/v0.1'
    allowed_executables = @('git','python','python.exe','python3','powershell','powershell.exe','pwsh','cmd','cmd.exe')
    readable_roots = @((Resolve-Path $WorkspaceRoot).Path)
    writable_roots = @((Resolve-Path $WorkspaceRoot).Path)
    max_timeout_seconds = 120
  } | ConvertTo-Json -Depth 5
  $policy | Set-Content -Encoding UTF8 -LiteralPath $policyPath
  Write-Host "Policy: created $policyPath"
} else {
  Write-Host "Policy: preserved existing $policyPath"
}

$provenancePath = Join-Path $InstallRoot 'runtime-provenance.json'
$provenance = @{
  schema = 'agentos.thin-client-runtime/v0.1'
  status = 'observed'
  source_ref = $SourceRef
  source_commit = $Ref
  path = $InstallRoot
  provenance_path = $provenancePath
  installed_at = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
} | ConvertTo-Json -Depth 4
$provenance | Set-Content -Encoding UTF8 -LiteralPath $provenancePath
Write-Host "Runtime provenance: $provenancePath"

$launcher = @"
@echo off
set "PYTHONPATH=$InstallRoot"
set "AGENTOS_CLIENT_HOME=$State"
"$pythonPath" -m agentos_node.client_cli %*
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
Write-Host "Source ref: $SourceRef"
Write-Host "Source commit: $Ref"
Write-Host "Python: $version"
Write-Host "Policy workspace: $WorkspaceRoot"
Write-Host "Shared state: $State"
Write-Host "Launcher: $launcherPath"

param(
  [string]$OneUrl = 'https://studio.milkcat.org/dashboard/api/agentos',
  [string]$NodeId = $env:COMPUTERNAME,
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$WorkspaceRoot = "$HOME\AgentOS",
  [string]$SourceRef = 'main',
  [int]$ApprovalTimeoutSeconds = 1800,
  [switch]$NoPythonInstall
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repo = 'alston-personal/agentmanager'

function Write-Step([string]$Message) {
  Write-Host ''
  Write-Host ('=== ' + $Message + ' ===') -ForegroundColor Cyan
}

function Test-RealPython([string]$Candidate) {
  if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
  if (-not (Test-Path -LiteralPath $Candidate)) { return $null }
  try {
    $out = @(& $Candidate -c "import sys; print('.'.join(map(str,sys.version_info[:3])))" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $out.Count -eq 0) { return $null }
    $v = ([string]$out[-1]).Trim()
    if ($v -notmatch '^(?<major>[0-9]+)\.[0-9]+\.[0-9]+$' -or [int]$Matches.major -lt 3) { return $null }
    return @{ Path=(Resolve-Path -LiteralPath $Candidate).Path; Version=$v }
  } catch { return $null }
}

function Find-RealPython {
  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($name in @('python','python3')) {
    $cmd=Get-Command $name -ErrorAction SilentlyContinue
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
    $r=Test-RealPython $candidate
    if ($r) { return $r }
  }
  return $null
}

function Ensure-Python {
  $python=Find-RealPython
  if ($python) { return $python }
  if ($NoPythonInstall) { throw 'Python 3 not found and automatic install is disabled.' }

  $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
  if (-not $winget) {
    throw 'Python 3 is not installed and winget is unavailable. Install Python 3 once, then rerun install-agentos.cmd.'
  }

  Write-Step 'Installing Python 3'
  $packages=@('Python.Python.3.13','Python.Python.3.12')
  foreach($package in $packages) {
    & $winget.Source install --id $package -e --scope user --silent --accept-package-agreements --accept-source-agreements
    $python=Find-RealPython
    if ($python) { return $python }
  }
  throw 'Automatic Python installation completed without exposing a usable python.exe.'
}

function Resolve-SourceCommit([string]$Ref) {
  $headers=@{
    'Accept'='application/vnd.github+json'
    'User-Agent'='AgentOS-OneClick-Installer/1.0'
    'Cache-Control'='no-cache'
  }
  $encoded=[uri]::EscapeDataString($Ref)
  $head=Invoke-RestMethod -UseBasicParsing -Headers $headers -Uri "https://api.github.com/repos/$Repo/commits/${encoded}?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
  $sha=[string]$head.sha
  if($sha -notmatch '^[0-9a-f]{40}$'){ throw "Could not resolve immutable source commit: $Ref" }
  return $sha
}

function Install-Supervisor([string]$PythonPath) {
  Write-Step 'Enabling AgentOS background service'
  $taskName='AgentOS Thin Client'
  $existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  if($existing){
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  }

  $state=Join-Path $InstallRoot 'state'
  $runner=Join-Path $InstallRoot 'agentos-thin-client-hidden.ps1'
  $log=Join-Path $InstallRoot 'thin-client.log'
  $escapedInstall=$InstallRoot.Replace("'","''")
  $escapedState=$state.Replace("'","''")
  $escapedPython=$PythonPath.Replace("'","''")
  $escapedLog=$log.Replace("'","''")
  $runnerBody=@(
    '$ErrorActionPreference=''Stop'''
    ('$env:PYTHONPATH=''' + $escapedInstall + '''')
    ('$env:AGENTOS_CLIENT_HOME=''' + $escapedState + '''')
    ('& ''' + $escapedPython + ''' -m agentos_node.client_cli run *>> ''' + $escapedLog + '''')
    'exit $LASTEXITCODE'
  ) -join [Environment]::NewLine
  $runnerBody | Set-Content -Encoding UTF8 -LiteralPath $runner

  # Use a hidden PowerShell host instead of cmd.exe so background restarts never
  # flash a console window in the signed-in user's desktop session.
  $action=New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"') `
    -WorkingDirectory $InstallRoot
  $trigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings=New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -Hidden
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'AgentOS Thin Client user-session daemon (headless)' -Force | Out-Null

  Start-ScheduledTask -TaskName $taskName
  Start-Sleep -Seconds 4
  $task=Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
  if($task.State -ne 'Running'){
    $info=Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
    throw "AgentOS Thin Client did not stay Running. LastTaskResult=$($info.LastTaskResult)"
  }
  $taskAction=(Get-ScheduledTask -TaskName $taskName).Actions | Select-Object -First 1
  if([string]$taskAction.Execute -match '(?i)cmd\.exe$'){
    throw 'AgentOS Thin Client task still uses visible cmd.exe'
  }
  Write-Host 'Background service: Running (headless)' -ForegroundColor Green
}

try {
  if($env:OS -ne 'Windows_NT'){ throw 'This one-click installer is for Windows only.' }
  if([string]::IsNullOrWhiteSpace($NodeId)){ throw 'NodeId could not be determined.' }

  Write-Host 'AgentOS Windows One-Click Installer' -ForegroundColor Green
  Write-Host "Node: $NodeId"
  Write-Host "ONE:  $OneUrl"

  $python=Ensure-Python
  Write-Host "Python: $($python.Version) ($($python.Path))"

  $sourceCommit=Resolve-SourceCommit $SourceRef
  Write-Host "Pinned source: $sourceCommit"

  $oldTask=Get-ScheduledTask -TaskName 'AgentOS Thin Client' -ErrorAction SilentlyContinue
  if($oldTask){
    Stop-ScheduledTask -TaskName 'AgentOS Thin Client' -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
  }

  # Scheduled Task may have spawned python.exe as a child. Stopping the task wrapper
  # does not reliably terminate that child on Windows, leaving AgentOS source files
  # locked during an in-place upgrade. Kill only AgentOS Thin Client processes.
  $agentProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match 'agentos_node\.client_cli' -and
      $_.CommandLine -match '\brun\b'
    }

  foreach($proc in $agentProcesses) {
    Write-Host ("Stopping stale AgentOS Thin Client process PID " + $proc.ProcessId)
    & taskkill.exe /PID $proc.ProcessId /T /F | Out-Null
  }

  if($agentProcesses) {
    $deadline=(Get-Date).AddSeconds(10)
    do {
      Start-Sleep -Milliseconds 300
      $stillRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
          $_.CommandLine -and
          $_.CommandLine -match 'agentos_node\.client_cli' -and
          $_.CommandLine -match '\brun\b'
        }
    } while($stillRunning -and (Get-Date) -lt $deadline)

    if($stillRunning) {
      $pids=($stillRunning | Select-Object -ExpandProperty ProcessId) -join ','
      throw "Stale AgentOS Thin Client process did not stop: PID(s) $pids"
    }
  }

  Write-Step 'Installing AgentOS Thin Client'
  $bootstrap=Join-Path $env:TEMP ("agentos-thin-client-" + $sourceCommit.Substring(0,12) + ".ps1")
  $raw="https://raw.githubusercontent.com/$Repo/$sourceCommit/scripts/install_thin_client_windows.ps1"
  Invoke-WebRequest -UseBasicParsing -Headers @{ 'Cache-Control'='no-cache' } -Uri $raw -OutFile $bootstrap
  & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $bootstrap -InstallRoot $InstallRoot -WorkspaceRoot $WorkspaceRoot -SourceRef $sourceCommit -PythonExe $python.Path
  if($LASTEXITCODE -ne 0){ throw "Thin Client file install failed with exit code $LASTEXITCODE" }

  $launcher=Join-Path $InstallRoot 'agentos-client.cmd'
  $state=Join-Path $InstallRoot 'state'
  $identity=Join-Path $state 'client.json'
  if(-not (Test-Path -LiteralPath $launcher)){ throw "Launcher missing after install: $launcher" }

  if(-not (Test-Path -LiteralPath $identity)){
    Write-Step 'Joining AgentOS Realm'
    Write-Host 'One approval code will appear below. Approve that code once; this installer will continue automatically.' -ForegroundColor Yellow
    & $launcher join --one $OneUrl --node-id $NodeId --expires-minutes 30 --timeout-seconds $ApprovalTimeoutSeconds
    if($LASTEXITCODE -ne 0){ throw "AgentOS join failed with exit code $LASTEXITCODE" }
    if(-not (Test-Path -LiteralPath $identity)){ throw 'Join returned without creating client.json.' }
  } else {
    $config=Get-Content -Raw -LiteralPath $identity | ConvertFrom-Json
    Write-Step 'Existing enrollment detected'
    Write-Host ("Realm: " + [string]$config.realm_id)
    Write-Host ("Node:  " + [string]$config.node_id)
    Write-Host 'Enrollment preserved; no new token or approval code will be created.' -ForegroundColor Green
  }

  Install-Supervisor $python.Path

  Write-Step 'Verifying end-to-end readiness'
  & $launcher verify
  if($LASTEXITCODE -ne 0){ throw "AgentOS readiness verification failed with exit code $LASTEXITCODE" }

  Write-Host ''
  Write-Host 'AGENTOS_ONE_CLICK_INSTALL=PASS' -ForegroundColor Green
  Write-Host 'AgentOS is installed, enrolled, running in the background, and readiness verification passed.' -ForegroundColor Green
  exit 0
}
catch {
  Write-Host ''
  Write-Host 'AGENTOS_ONE_CLICK_INSTALL=FAIL' -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  exit 1
}

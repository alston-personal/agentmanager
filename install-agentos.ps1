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
  if($Ref -match '^[0-9a-fA-F]{40}$'){
    return $Ref.ToLowerInvariant()
  }
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

function Install-UserRuntime([string]$Runner) {
  $runKey='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
  $watchdog=Join-Path $InstallRoot 'scripts\windows\user_runtime_watchdog.ps1'
  if(-not (Test-Path -LiteralPath $watchdog)){
    throw "Per-user watchdog script missing: $watchdog"
  }

  New-Item -Path $runKey -Force | Out-Null
  $clientRun='powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Runner + '"'
  $watchdogRun='powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $watchdog + '" -Runner "' + $Runner + '"'
  New-ItemProperty -Path $runKey -Name 'AgentOS Thin Client User' -Value $clientRun -PropertyType String -Force | Out-Null
  New-ItemProperty -Path $runKey -Name 'AgentOS Thin Client Watchdog User' -Value $watchdogRun -PropertyType String -Force | Out-Null

  Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
    '-NoProfile',
    '-NonInteractive',
    '-WindowStyle','Hidden',
    '-ExecutionPolicy','Bypass',
    '-File',$watchdog,
    '-Runner',$Runner
  )
  Start-Sleep -Seconds 4

  $running=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match 'agentos_node\.client_cli' -and
      $_.CommandLine -match '\brun\b'
    } |
    Select-Object -First 1
  if(-not $running){ throw 'Per-user hidden Thin Client did not start' }

  $clientValue=[string](Get-ItemPropertyValue -Path $runKey -Name 'AgentOS Thin Client User')
  $watchdogValue=[string](Get-ItemPropertyValue -Path $runKey -Name 'AgentOS Thin Client Watchdog User')
  if($clientValue -notmatch '(?i)-WindowStyle\s+Hidden'){
    throw 'Per-user Thin Client autorun is not hidden'
  }
  if($watchdogValue -notmatch '(?i)-WindowStyle\s+Hidden'){
    throw 'Per-user watchdog autorun is not hidden'
  }

  Write-Host 'Background service: Running (headless, per-user)' -ForegroundColor Green
  Write-Host 'Independent watchdog: Running (hidden, per-user 60s cadence)' -ForegroundColor Green
}

function Install-Supervisor([string]$PythonPath) {
  Write-Step 'Enabling AgentOS background service'
  $taskName='AgentOS Thin Client'
  $watchdogTaskName='AgentOS Thin Client Watchdog'
  $fallbackTaskName='AgentOS Thin Client User'
  $fallbackWatchdogTaskName='AgentOS Thin Client Watchdog User'

  $existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  if($existing){
    # Never revive a legacy visible task during recovery. Stop first; the
    # canonical hidden action is re-registered below before any start occurs.
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  }

  # Replace legacy supervisor artifacts with the canonical hidden Thin Client +
  # independent watchdog pair. The watchdog must not share process lifetime with
  # the client it supervises.
  foreach($legacyTask in @($watchdogTaskName,'AgentOS Thin Client Headless Switch')){
    $legacy=Get-ScheduledTask -TaskName $legacyTask -ErrorAction SilentlyContinue
    if($legacy){
      Stop-ScheduledTask -TaskName $legacyTask -ErrorAction SilentlyContinue
      try { Disable-ScheduledTask -TaskName $legacyTask -ErrorAction Stop | Out-Null } catch {}
      try {
        Unregister-ScheduledTask -TaskName $legacyTask -Confirm:$false -ErrorAction Stop
      } catch {
        Write-Host ("Legacy task retained disabled because its ACL does not allow removal: " + $legacyTask) -ForegroundColor Yellow
      }
    }
  }
  foreach($legacyScript in @(
    (Join-Path $InstallRoot 'agentos-thin-client-watchdog.ps1'),
    (Join-Path $InstallRoot 'agentos-headless-switch.ps1')
  )){
    Remove-Item -LiteralPath $legacyScript -Force -ErrorAction SilentlyContinue
  }

  $state=Join-Path $InstallRoot 'state'
  $runner=Join-Path $InstallRoot 'agentos-thin-client-hidden.ps1'
  $log=Join-Path $InstallRoot 'thin-client.log'
  $watchdogScript=Join-Path $InstallRoot 'scripts\windows\thin_client_watchdog.ps1'
  if(-not (Test-Path -LiteralPath $watchdogScript)){
    throw "AgentOS Thin Client watchdog script missing: $watchdogScript"
  }

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

  # Primary Thin Client: hidden, interactive-user session so GUI capabilities
  # remain available, with normal Task Scheduler restart-on-failure semantics.
  $action=New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"') `
    -WorkingDirectory $InstallRoot
  $trigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings=New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -Hidden
  try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'AgentOS Thin Client user-session daemon (headless)' -Force -ErrorAction Stop | Out-Null
  } catch {
    $accessDenied=($_.Exception.HResult -eq -2147024891) -or
      ($_.FullyQualifiedErrorId -match '(?i)unauthorized|accessdenied') -or
      ($_.Exception.Message -match '(?i)access.*denied|unauthorized')
    if(-not $accessDenied){
      throw
    }
    Write-Host 'Task Scheduler ACL blocks non-admin repair; switching to per-user hidden runtime.' -ForegroundColor Yellow
    Install-UserRuntime -Runner $runner
    return
  }

  $registeredAction=(Get-ScheduledTask -TaskName $taskName -ErrorAction Stop).Actions | Select-Object -First 1
  if([string]$registeredAction.Execute -match '(?i)cmd\.exe$'){
    throw 'Refusing to start visible cmd.exe Thin Client task after repair'
  }
  if([string]$registeredAction.Execute -notmatch '(?i)powershell\.exe$' -or [string]$registeredAction.Arguments -notmatch '(?i)-WindowStyle\s+Hidden'){
    throw 'Refusing to start Thin Client task unless its registered action is hidden PowerShell'
  }

  # Independent watchdog: a separate periodic task is required because an
  # intentional Stop-ScheduledTask is not a process failure and therefore does
  # not reliably activate RestartCount on the primary task.
  $watchdogArgs='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $watchdogScript + '" -TaskName "' + $taskName + '" -InstallRoot "' + $InstallRoot + '"'
  $watchdogAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $watchdogArgs -WorkingDirectory $InstallRoot
  $watchdogLogonTrigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $watchdogPeriodicTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
  $watchdogSettings=New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -Hidden
  try {
    Register-ScheduledTask -TaskName $watchdogTaskName -Action $watchdogAction -Trigger @($watchdogLogonTrigger,$watchdogPeriodicTrigger) -Settings $watchdogSettings -Description 'AgentOS Thin Client independent liveness watchdog' -Force -ErrorAction Stop | Out-Null
  } catch {
    $accessDenied=($_.Exception.HResult -eq -2147024891) -or
      ($_.FullyQualifiedErrorId -match '(?i)unauthorized|accessdenied') -or
      ($_.Exception.Message -match '(?i)access.*denied|unauthorized')
    if(-not $accessDenied){
      throw
    }
    $watchdogTaskName=$fallbackWatchdogTaskName
    $watchdogArgs='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $watchdogScript + '" -TaskName "' + $taskName + '" -InstallRoot "' + $InstallRoot + '"'
    $watchdogAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $watchdogArgs -WorkingDirectory $InstallRoot
    Write-Host ("Protected legacy watchdog ACL detected; using user-owned fallback: " + $watchdogTaskName) -ForegroundColor Yellow
    Register-ScheduledTask -TaskName $watchdogTaskName -Action $watchdogAction -Trigger @($watchdogLogonTrigger,$watchdogPeriodicTrigger) -Settings $watchdogSettings -Description 'AgentOS Thin Client independent liveness watchdog' -Force -ErrorAction Stop | Out-Null
  }

  $registeredWatchdogAction=(Get-ScheduledTask -TaskName $watchdogTaskName -ErrorAction Stop).Actions | Select-Object -First 1
  if([string]$registeredWatchdogAction.Execute -notmatch '(?i)powershell\.exe$' -or [string]$registeredWatchdogAction.Arguments -notmatch '(?i)-WindowStyle\s+Hidden'){
    throw 'Refusing to start watchdog unless its registered action is hidden PowerShell'
  }

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

  $watchdogTask=Get-ScheduledTask -TaskName $watchdogTaskName -ErrorAction Stop
  $watchdogActionActual=$watchdogTask.Actions | Select-Object -First 1
  if([string]$watchdogActionActual.Execute -notmatch '(?i)powershell\.exe$'){
    throw 'AgentOS Thin Client watchdog is not using hidden PowerShell'
  }
  if([string]$watchdogActionActual.Arguments -notmatch 'thin_client_watchdog\.ps1'){
    throw 'AgentOS Thin Client watchdog action is not wired to the canonical script'
  }

  Write-Host 'Background service: Running (headless)' -ForegroundColor Green
  Write-Host 'Independent watchdog: Installed (60s cadence)' -ForegroundColor Green
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
  $oldWatchdog=Get-ScheduledTask -TaskName 'AgentOS Thin Client Watchdog' -ErrorAction SilentlyContinue

  # Stop the watchdog first. Otherwise it can race the repair by immediately
  # restarting the Thin Client after we terminate it, re-locking source files
  # while the installer is overwriting them.
  if($oldWatchdog){
    Stop-ScheduledTask -TaskName 'AgentOS Thin Client Watchdog' -ErrorAction SilentlyContinue
    Disable-ScheduledTask -TaskName 'AgentOS Thin Client Watchdog' -ErrorAction SilentlyContinue | Out-Null
  }

  if($oldTask){
    Stop-ScheduledTask -TaskName 'AgentOS Thin Client' -ErrorAction SilentlyContinue
    Disable-ScheduledTask -TaskName 'AgentOS Thin Client' -ErrorAction SilentlyContinue | Out-Null
  }

  Start-Sleep -Seconds 1

  # Scheduled Task may have spawned python.exe as a child. Stopping the task wrapper
  # does not reliably terminate that child on Windows, leaving AgentOS source files
  # locked during an in-place upgrade. Kill only AgentOS Thin Client processes.
  function Get-AgentOSThinClientProcesses {
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        if (-not $_.CommandLine) { return $false }
        $cmd=[string]$_.CommandLine
        $isClient =
          ($cmd -match 'agentos_node\.client_cli') -or
          ($cmd -match 'agentos-client\.cmd') -or
          ($cmd -match 'AgentOS\\agentos_node\\thin_client\.py') -or
          (($cmd -match '(?i)python(?:\.exe)?') -and ($cmd -match '(?i)AgentOS') -and ($cmd -match '(?i)client_cli|thin_client'))
        $isRun =
          ($cmd -match '(?i)(^|\s|")run($|\s|")') -or
          ($cmd -match '(?i)client_cli.*run') -or
          ($cmd -match '(?i)thin_client')
        return ($isClient -and $isRun)
      }
  }

  $agentProcesses = @(Get-AgentOSThinClientProcesses)

  foreach($proc in $agentProcesses) {
    Write-Host ("Stopping stale AgentOS Thin Client process PID " + $proc.ProcessId)
    & taskkill.exe /PID $proc.ProcessId /T /F | Out-Null
  }

  if($agentProcesses.Count -gt 0) {
    $deadline=(Get-Date).AddSeconds(10)
    do {
      Start-Sleep -Milliseconds 300
      $stillRunning = @(Get-AgentOSThinClientProcesses)
    } while($stillRunning.Count -gt 0 -and (Get-Date) -lt $deadline)

    if($stillRunning.Count -gt 0) {
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

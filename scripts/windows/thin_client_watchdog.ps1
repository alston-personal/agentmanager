param(
  [string]$TaskName = "AgentOS Thin Client",
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [int]$HeartbeatStaleSeconds = 180,
  [int]$MinRestartSeconds = 45
)

$ErrorActionPreference = "Stop"
$stateDir = Join-Path $InstallRoot "watchdog"
$stateFile = Join-Path $stateDir "state.json"
$logFile = Join-Path $stateDir "watchdog.log"
$heartbeatFile = Join-Path $InstallRoot "state\heartbeat.json"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Write-Log([string]$Message) {
  $line = "{0} {1}" -f ([DateTimeOffset]::UtcNow.ToString("o")), $Message
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Get-AgentOSClientProcess {
  return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match 'agentos_node\.client_cli' -and
      $_.CommandLine -match '\brun\b'
    } |
    Select-Object -First 1
}

function Test-HeartbeatFresh {
  if (-not (Test-Path -LiteralPath $heartbeatFile)) {
    return $false
  }
  try {
    $item = Get-Item -LiteralPath $heartbeatFile -ErrorAction Stop
    $age = ([DateTime]::UtcNow - $item.LastWriteTimeUtc).TotalSeconds
    return ($age -le $HeartbeatStaleSeconds)
  } catch {
    return $false
  }
}

$managedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$running = Get-AgentOSClientProcess
$heartbeatFresh = Test-HeartbeatFresh

if ($managedTask -and [string]$managedTask.State -eq 'Running' -and $running -and $heartbeatFresh) {
  exit 0
}

$reason = @()
if (-not $managedTask) {
  $reason += "task_missing"
} elseif ([string]$managedTask.State -ne 'Running') {
  $reason += ("task_state=" + [string]$managedTask.State)
}
if (-not $running) {
  $reason += "process_missing"
}
if (-not $heartbeatFresh) {
  if (Test-Path -LiteralPath $heartbeatFile) {
    try {
      $age = [int](([DateTime]::UtcNow - (Get-Item -LiteralPath $heartbeatFile).LastWriteTimeUtc).TotalSeconds)
      $reason += ("heartbeat_stale_seconds=" + $age)
    } catch {
      $reason += "heartbeat_unreadable"
    }
  } else {
    $reason += "heartbeat_missing"
  }
}

$now = [DateTimeOffset]::UtcNow
$last = $null
if (Test-Path -LiteralPath $stateFile) {
  try {
    $doc = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
    if ($doc.last_restart_at) {
      $last = [DateTimeOffset]::Parse([string]$doc.last_restart_at)
    }
  } catch {}
}
if ($last -and (($now - $last).TotalSeconds -lt $MinRestartSeconds)) {
  Write-Log ("restart_suppressed rate_limit_seconds={0} reason={1}" -f $MinRestartSeconds, ($reason -join ','))
  exit 0
}

try {
  if (-not $managedTask) {
    throw "Managed task not found: $TaskName"
  }

  # A stale heartbeat with a still-running process is treated as a wedged client.
  # Stop only the AgentOS Thin Client task/process; unrelated user processes remain untouched.
  if ($running -and -not $heartbeatFresh) {
    Write-Log ("stale_client_restart pid={0} reason={1}" -f $running.ProcessId, ($reason -join ','))
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    $remaining = Get-AgentOSClientProcess
    if ($remaining) {
      & taskkill.exe /PID $remaining.ProcessId /T /F | Out-Null
    }
    Start-Sleep -Milliseconds 500
  }

  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  @{
    last_restart_at = $now.ToString("o")
    task = $TaskName
    result = "started"
    reason = ($reason -join ',')
  } | ConvertTo-Json -Compress | Set-Content -LiteralPath $stateFile -Encoding UTF8
  Write-Log ("restart_requested task={0} reason={1}" -f $TaskName, ($reason -join ','))
} catch {
  @{
    last_restart_at = $now.ToString("o")
    task = $TaskName
    result = "error"
    reason = ($reason -join ',')
    error = $_.Exception.Message
  } | ConvertTo-Json -Compress | Set-Content -LiteralPath $stateFile -Encoding UTF8
  Write-Log ("restart_error task={0} reason={1} error={2}" -f $TaskName, ($reason -join ','), $_.Exception.Message)
  throw
}

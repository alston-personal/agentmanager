param(
  [string]$TaskName = "AgentOS Thin Client",
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [int]$MinRestartSeconds = 45,
  [int]$HeartbeatStaleSeconds = 45
)

$ErrorActionPreference = "Stop"
$stateDir = Join-Path $InstallRoot "watchdog"
$stateFile = Join-Path $stateDir "state.json"
$logFile = Join-Path $stateDir "watchdog.log"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Write-Log([string]$Message) {
  $line = "{0} {1}" -f ([DateTimeOffset]::UtcNow.ToString("o")), $Message
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

# A live PID is not enough: a hung Thin Client can keep its process while
# heartbeat delivery has stopped. The client writes this lease after each
# successful ONE heartbeat, so watchdog can detect a stale daemon independently.
$managedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'agentos_node\.client_cli.*run|agentos-client(?:\.exe)?.*run' } |
  Select-Object -First 1

$leaseFile = Join-Path $env:USERPROFILE ".agentos\heartbeat-lease.json"
$heartbeatStale = $false
$heartbeatAgeSeconds = $null
if (Test-Path $leaseFile) {
  try {
    $lease = Get-Content -Raw -LiteralPath $leaseFile | ConvertFrom-Json
    if ($lease.recorded_at_unix) {
      $leaseUtc = [DateTimeOffset]::FromUnixTimeSeconds([int64]$lease.recorded_at_unix)
      $heartbeatAgeSeconds = ([DateTimeOffset]::UtcNow - $leaseUtc).TotalSeconds
      if ($heartbeatAgeSeconds -gt $HeartbeatStaleSeconds) {
        $heartbeatStale = $true
      }
    }
  } catch {
    Write-Log ("heartbeat_lease_parse_error error={0}" -f $_.Exception.Message)
  }
}

if ($running -and -not $heartbeatStale) {
  exit 0
}

if ($running -and $heartbeatStale) {
  Write-Log ("heartbeat_stale pid={0} age_seconds={1:n1} threshold={2}" -f $running.ProcessId,$heartbeatAgeSeconds,$HeartbeatStaleSeconds)
  try {
    Stop-Process -Id $running.ProcessId -Force -ErrorAction Stop
    Start-Sleep -Milliseconds 500
  } catch {
    Write-Log ("hung_process_stop_error pid={0} error={1}" -f $running.ProcessId,$_.Exception.Message)
  }
  try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
}

$now = [DateTimeOffset]::UtcNow
$last = $null
if (Test-Path $stateFile) {
  try {
    $doc = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
    if ($doc.last_restart_at) {
      $last = [DateTimeOffset]::Parse([string]$doc.last_restart_at)
    }
  } catch {}
}
if ($last -and (($now - $last).TotalSeconds -lt $MinRestartSeconds)) {
  Write-Log "restart_suppressed rate_limit_seconds=$MinRestartSeconds"
  exit 0
}

try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  @{ last_restart_at=$now.ToString("o"); task=$TaskName; result="started" } |
    ConvertTo-Json -Compress |
    Set-Content -LiteralPath $stateFile -Encoding UTF8
  Write-Log "restart_requested task=$TaskName"
} catch {
  @{ last_restart_at=$now.ToString("o"); task=$TaskName; result="error"; error=$_.Exception.Message } |
    ConvertTo-Json -Compress |
    Set-Content -LiteralPath $stateFile -Encoding UTF8
  Write-Log ("restart_error task={0} error={1}" -f $TaskName, $_.Exception.Message)
  throw
}

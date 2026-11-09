param(
  [string]$TaskName = "AgentOS Thin Client",
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [int]$MinRestartSeconds = 45
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

# Task Scheduler is the primary local source of truth for the managed client.
# Process command-line inspection is only a fallback because CommandLine may be
# unavailable/transient under some Windows session boundaries.
$managedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($managedTask -and [string]$managedTask.State -eq 'Running') {
  exit 0
}

$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'agentos_node\.client_cli.*run|agentos-client(?:\.exe)?.*run' } |
  Select-Object -First 1

if ($running) {
  Write-Log "task_state_not_running_but_process_present pid=$($running.ProcessId)"
  exit 0
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

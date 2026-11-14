# Transactional cutover for a pre-approved, verified staged Realm identity.
# Run only with explicit operator authorization on the owning Windows device.
# Does not migrate Realm data or authorize a Node in the destination Realm.
param(
  [Parameter(Mandatory=$true)][string]$StageRoot,
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [switch]$CommitApproved
)
$ErrorActionPreference = 'Stop'
if (-not $CommitApproved) { throw 'Explicit -CommitApproved is required for active Node cutover' }

$root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$stage = [IO.Path]::GetFullPath($StageRoot).TrimEnd('\')
$local = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')
$stageParent = [IO.Path]::GetDirectoryName($stage)
if ($stageParent -ine $local -or
    -not [IO.Path]::GetFileName($stage).StartsWith('AgentOS-realm-stage-', [StringComparison]::OrdinalIgnoreCase) -or
    $stage -ieq $root) { throw 'StageRoot must be an independent AgentOS-realm-stage directory in LOCALAPPDATA' }

$state = Join-Path $root 'state'
$originalFile = Join-Path $state 'client.json'
$stageFile = Join-Path (Join-Path $stage 'state') 'client.stage.json'
$stageLease = Join-Path (Join-Path $stage 'state') 'heartbeat-lease.json'
$launcher = Join-Path $root 'agentos-client.cmd'
$stageLauncher = Join-Path $stage 'agentos-client.cmd'
foreach($file in @($originalFile,$stageFile,$stageLease,$launcher,$stageLauncher)) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required binding or launcher missing: $file" }
}
# Reject filesystem indirection before reading credentials or stopping services.
# A symlink/junction in either state path could redirect the atomic swap.
foreach($candidate in @($root,$state,$stage,(Join-Path $stage 'state'),
                      $originalFile,$stageFile,$stageLease,$launcher,$stageLauncher)) {
  $item = Get-Item -LiteralPath $candidate -Force -ErrorAction Stop
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Realm cutover refuses reparse-point credentials, roots, or launchers'
  }
}

# A previous interrupted transfer must be reconciled before any new cutover.
# The journal is only a local crash marker, NOT ONE approval or a signed Receipt.
$pendingJournal = Join-Path $state 'realm-transfer-pending.json'
if (Test-Path -LiteralPath $pendingJournal) {
  throw 'Pending Realm transfer requires governed reconciliation before another cutover'
}

$original = Get-Content -Raw -LiteralPath $originalFile | ConvertFrom-Json
$target = Get-Content -Raw -LiteralPath $stageFile | ConvertFrom-Json
$lease = Get-Content -Raw -LiteralPath $stageLease | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace([string]$original.node_token) -or
    [string]::IsNullOrWhiteSpace([string]$original.realm_id) -or
    [string]::IsNullOrWhiteSpace([string]$original.node_id) -or
    [string]$original.node_id -ne [string]$target.node_id -or
    [string]$original.realm_id -eq [string]$target.realm_id -or
    [string]::IsNullOrWhiteSpace([string]$target.node_token) -or
    [string]$target.realm_id -notmatch '^realm-u-[0-9a-f]{24}$' -or
    [string]$target.one_url -ne 'https://agentos.milkcat.org') {
  throw 'Staged identity does not match the authorized Node/tenant rebind contract'
}
if ($lease.schema -ne 'agentos.node-heartbeat-lease/v0.1' -or
    $lease.realm_id -ne $target.realm_id -or $lease.node_id -ne $target.node_id -or
    $lease.one_url -ne $target.one_url -or
    ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$lease.recorded_at_unix) -gt 600 -or
    ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$lease.recorded_at_unix) -lt -30) {
  throw 'Staged target heartbeat evidence is missing, mismatched or stale'
}
# Reauthenticate target bearer before stopping the original Node.
& $stageLauncher --config $stageFile health | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Staged target Realm is not reachable using the claimed credential' }
& $launcher health | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Original Realm health not available; refusing an unverified rollback basis' }

# This transaction is only safe with the canonical hidden task pair. Unknown
# task layouts must not be stopped or replaced by guessing.
$primaryName = 'AgentOS Thin Client'
$watchdogName = 'AgentOS Thin Client Watchdog'
$primary = Get-ScheduledTask -TaskName $primaryName -ErrorAction SilentlyContinue
$watchdog = Get-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue
if ($null -eq $primary) {
  throw 'Canonical hidden Windows supervisor not found; manual governance needed'
}
# Current one-click installer has a single hidden task. Older supervised
# installs have a second watchdog; when present it too must be a known action.
if (@($primary.Actions).Count -ne 1 -or
    $primary.Actions[0].Execute -notmatch '(?i)powershell' -or
    $primary.Actions[0].Arguments -notmatch '(?i)-WindowStyle\s+Hidden' -or
    $primary.Actions[0].Arguments -notmatch 'agentos-thin-client-hidden' -or
    ($null -ne $watchdog -and (
      @($watchdog.Actions).Count -ne 1 -or
      $watchdog.Actions[0].Execute -notmatch '(?i)powershell' -or
      $watchdog.Actions[0].Arguments -notmatch 'watchdog'))) {
  throw 'Unknown Windows supervisor action; refusing to replace an active Node'
}
$hasWatchdog = ($null -ne $watchdog)

# Durable, redacted intent marker is persisted before stopping the original Node.
# CreateNew refuses a concurrent transfer; a crash leaves this marker for inspection.
$transferId = [guid]::NewGuid().ToString('N')
$sourceHash = (Get-FileHash -LiteralPath $originalFile -Algorithm SHA256).Hash
$targetHash = (Get-FileHash -LiteralPath $stageFile -Algorithm SHA256).Hash
$pending = @{
  schema = 'agentos.node-realm-transfer-local-pending/v1'
  transfer_id = $transferId
  node_id = [string]$original.node_id
  source_realm_id = [string]$original.realm_id
  target_realm_id = [string]$target.realm_id
  source_sha256 = $sourceHash
  target_sha256 = $targetHash
  created_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
  state = 'CUTOVER_UNRESOLVED'
}
$journalBytes = [Text.Encoding]::UTF8.GetBytes(($pending | ConvertTo-Json -Compress))
$journalStream = [IO.File]::Open($pendingJournal, [IO.FileMode]::CreateNew,
                                 [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
  $journalStream.Write($journalBytes, 0, $journalBytes.Length)
  $journalStream.Flush($true)
} finally {
  $journalStream.Dispose()
}

function Complete-LocalRealmTransfer([string]$Outcome) {
  # A local outcome never attests ONE cross-Realm governance approval.
  $localResult = @{ schema='agentos.node-realm-transfer-local-result/v1';
                    transfer_id=$transferId; node_id=[string]$original.node_id;
                    source_realm_id=[string]$original.realm_id;
                    target_realm_id=[string]$target.realm_id;
                    outcome=$Outcome; recorded_at_utc=[DateTimeOffset]::UtcNow.ToString('o');
                    one_receipt_attested=$false }
  $resultFile = Join-Path $state 'realm-transfer-last-local-result.json'
  $resultTemp = Join-Path $state ('realm-transfer-local-result-' + $transferId + '.tmp')
  try {
    [IO.File]::WriteAllText($resultTemp, ($localResult | ConvertTo-Json -Compress), [Text.Encoding]::UTF8)
    if (Test-Path -LiteralPath $resultFile) {
      $resultBackup = Join-Path $state ('realm-transfer-previous-result-' + $transferId + '.bak')
      [IO.File]::Replace($resultTemp, $resultFile, $resultBackup)
    } else {
      [IO.File]::Move($resultTemp, $resultFile)
    }
    Remove-Item -LiteralPath $pendingJournal -Force -ErrorAction Stop
  } finally {
    Remove-Item -LiteralPath $resultTemp -Force -ErrorAction SilentlyContinue
  }
}

$backup = Join-Path $state ('client.realm-rollback-' + [guid]::NewGuid().ToString('N') + '.json')
$temp = Join-Path $state ('client.stage-swap-' + [guid]::NewGuid().ToString('N') + '.tmp')
$committed = $false
$stopped = $false
try {
  $stopped = $true
  if ($hasWatchdog) { Stop-ScheduledTask -TaskName $watchdogName -ErrorAction Stop }
  Stop-ScheduledTask -TaskName $primaryName -ErrorAction Stop
  Start-Sleep -Seconds 2
  if ((Get-ScheduledTask -TaskName $primaryName).State -eq 'Running' -or
      ($hasWatchdog -and (Get-ScheduledTask -TaskName $watchdogName).State -eq 'Running')) {
    throw 'Supervisor failed to stop cleanly'
  }
  # Task Scheduler may stop the wrapper before the Python child exits.
  $stragglers = @(Get-CimInstance Win32_Process -ErrorAction Stop |
    Where-Object { $_.Name -match '^(python|pythonw)([0-9]+)?\.exe$' -and
                   $_.CommandLine -match 'agentos_node\.client_cli\s+run' })
  if ($stragglers.Count -gt 0) {
    throw 'Thin Client daemon still running after task stop; refusing credential swap'
  }
  # In-place copy is forbidden. Keep the exact original bytes for rollback.
  Copy-Item -LiteralPath $stageFile -Destination $temp -ErrorAction Stop
  # File.Replace atomically installs the new file AND captures old bytes.
  [IO.File]::Replace($temp, $originalFile, $backup)
  $committed = $true
  Start-ScheduledTask -TaskName $primaryName -ErrorAction Stop
  if ($hasWatchdog) { Start-ScheduledTask -TaskName $watchdogName -ErrorAction Stop }
  Start-Sleep -Seconds 3
  if ((Get-ScheduledTask -TaskName $primaryName).State -ne 'Running') {
    throw 'Target supervisor did not restart'
  }
  # Recheck the live active configuration through the original launcher,
  # then cause a fresh authenticated heartbeat on the destination Realm.
  & $launcher health | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'New active credential health failed' }
  $pythonExe = $null
  $launcherText = Get-Content -Raw -LiteralPath $launcher
  if ($launcherText -match '(?m)^"([^"]+\.exe)" -m agentos_node\.client_cli') {
    $pythonExe = $Matches[1]
  }
  if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Unable to verify active Node heartbeat with its pinned interpreter'
  }
  $oldPythonPath = $env:PYTHONPATH
  $oldHome = $env:AGENTOS_CLIENT_HOME
  try {
    $env:PYTHONPATH = $root
    $env:AGENTOS_CLIENT_HOME = $state
    $probe = 'from agentos_node.client_cli import _load_policy,build_client; from agentos_node.thin_client_transport import ClientConfig; from pathlib import Path; c=ClientConfig.load(Path("state")/"client.json"); t=build_client(c,_load_policy(Path("state")/"policy.json")); r=t.heartbeat(); raise SystemExit(0 if r.get("heartbeat_recorded") else 2)'
    Push-Location $root
    try { & $pythonExe -c $probe | Out-Null } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'New active Realm heartbeat was not acknowledged' }
  } finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:AGENTOS_CLIENT_HOME = $oldHome
  }
  Complete-LocalRealmTransfer 'COMMITTED_LOCAL_HEARTBEAT_VERIFIED'
  Write-Host 'agentos_realm_switch=COMMITTED_VERIFIED'
  Write-Host "agentos_node_id=$($target.node_id)"
  Write-Host "agentos_realm_id=$($target.realm_id)"
  Write-Host 'agentos_active_binding=TARGET'
  # Backup intentionally retained for manual incident recovery.
} catch {
  $failure = $_.Exception.Message
  if ($stopped) {
    if ($hasWatchdog) { Stop-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue }
    Stop-ScheduledTask -TaskName $primaryName -ErrorAction SilentlyContinue
    if ($committed -and (Test-Path -LiteralPath $backup)) {
      try {
        $failedTarget = Join-Path $state ('client.failed-cutover-' + [guid]::NewGuid().ToString('N') + '.json')
        [IO.File]::Replace($backup, $originalFile, $failedTarget)
      } catch {
        # Never skip recovery restart if an atomic reverse-swap itself fails.
        Write-Host 'agentos_rollback_swap=FAILED'
      }
    }
    Start-ScheduledTask -TaskName $primaryName -ErrorAction SilentlyContinue
    if ($hasWatchdog) { Start-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue }
  }
  $restored = $false
  try {
    $check = Get-Content -Raw -LiteralPath $originalFile | ConvertFrom-Json
    $restored = ([string]$check.realm_id -eq [string]$original.realm_id -and
                 [string]$check.node_id -eq [string]$original.node_id -and
                 [string]$check.node_token -eq [string]$original.node_token)
    if ($restored) {
      & $launcher health | Out-Null
      $restored = ($LASTEXITCODE -eq 0 -and (Get-ScheduledTask -TaskName $primaryName).State -eq 'Running')
    }
  } catch { $restored = $false }
  if ($restored) {
    Complete-LocalRealmTransfer 'ROLLED_BACK_LOCAL_HEALTH_VERIFIED'
    Write-Host 'agentos_realm_switch=ROLLED_BACK_VERIFIED'
    Write-Host 'agentos_active_binding=ORIGINAL'
  } else {
    Write-Host 'agentos_realm_switch=ROLLBACK_UNVERIFIED'
    Write-Host 'agentos_active_binding=REQUIRES_OPERATOR_REVIEW'
  }
  throw "Realm cutover not accepted: $failure"
} finally {
  Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
}

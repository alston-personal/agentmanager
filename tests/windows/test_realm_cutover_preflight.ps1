# Guard-only negative tests. Never calls live ONE, Scheduler, or Task Scheduler.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script = Join-Path $repo 'scripts/windows/commit_staged_realm.ps1'
$temp = Join-Path $env:RUNNER_TEMP ('realm-transfer-negative-' + [guid]::NewGuid().ToString('N'))
$oldLocal = $env:LOCALAPPDATA
try {
  $env:LOCALAPPDATA = $temp
  $root = Join-Path $temp 'AgentOS'
  $stage = Join-Path $temp 'AgentOS-realm-stage-check'
  $state = Join-Path $root 'state'
  $stageState = Join-Path $stage 'state'
  New-Item -ItemType Directory -Force -Path $state,$stageState | Out-Null
  Set-Content -LiteralPath (Join-Path $root 'agentos-client.cmd') -Value '@echo off' -Encoding Ascii
  Set-Content -LiteralPath (Join-Path $stage 'agentos-client.cmd') -Value '@echo off' -Encoding Ascii
  $realmA = 'realm-u-' + ('a' * 24)
  $realmB = 'realm-u-' + ('b' * 24)
  $original = @{node_id='custom-id';realm_id=$realmA;node_token='tokenA';one_url='https://agentos.milkcat.org'}
  $target = @{node_id='custom-id';realm_id=$realmB;node_token='tokenB';one_url='https://agentos.milkcat.org'}
  $lease = @{schema='agentos.node-heartbeat-lease/v0.1';node_id='custom-id';realm_id=$realmB;one_url='https://agentos.milkcat.org';recorded_at_unix=0}
  $originalPath = Join-Path $state 'client.json'
  $targetPath = Join-Path $stageState 'client.stage.json'
  $leasePath = Join-Path $stageState 'heartbeat-lease.json'
  $original | ConvertTo-Json | Set-Content -LiteralPath $originalPath -Encoding UTF8
  $target | ConvertTo-Json | Set-Content -LiteralPath $targetPath -Encoding UTF8
  $lease | ConvertTo-Json | Set-Content -LiteralPath $leasePath -Encoding UTF8
  $baseline = (Get-FileHash -LiteralPath $originalPath -Algorithm SHA256).Hash

  function Assert-Blocked([string]$expected, [bool]$approved=$true) {
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script,'-InstallRoot',$root,'-StageRoot',$stage)
    if ($approved) { $args += '-CommitApproved' }
    $savedPreference = $ErrorActionPreference
    try {
      # Windows PowerShell 5 treats stderr of a failing native subprocess as a
      # terminating NativeCommandError when the caller uses Stop.
      $ErrorActionPreference = 'Continue'
      $result = & powershell.exe @args 2>&1 | Out-String
      $exitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $savedPreference
    }
    if ($exitCode -eq 0) { throw "Cutover unexpectedly passed preflight: $expected" }
    if ($result -notlike "*$expected*") { throw "Missing expected rejection: $expected; output=$result" }
    if ((Get-FileHash -LiteralPath $originalPath -Algorithm SHA256).Hash -ne $baseline) {
      throw 'Guard changed active credential bytes'
    }
  }
  Assert-Blocked 'Explicit -CommitApproved is required' $false
  Assert-Blocked 'Staged target heartbeat evidence is missing'
  $original.node_token = ''
  $original | ConvertTo-Json | Set-Content -LiteralPath $originalPath -Encoding UTF8
  $baseline = (Get-FileHash -LiteralPath $originalPath -Algorithm SHA256).Hash
  Assert-Blocked 'Staged identity does not match'
  $original.node_token = 'tokenA'
  $original | ConvertTo-Json | Set-Content -LiteralPath $originalPath -Encoding UTF8
  $baseline = (Get-FileHash -LiteralPath $originalPath -Algorithm SHA256).Hash
  $target.node_id = 'other-node'
  $target | ConvertTo-Json | Set-Content -LiteralPath $targetPath -Encoding UTF8
  Assert-Blocked 'Staged identity does not match'

  # Simulate an interrupted previous transaction: new transfers must fail closed.
  $pendingPath = Join-Path $state 'realm-transfer-pending.json'
  Set-Content -LiteralPath $pendingPath -Encoding UTF8 -Value '{"schema":"agentos.node-realm-transfer-local-pending/v1","state":"CUTOVER_UNRESOLVED"}'
  Assert-Blocked 'Pending Realm transfer requires governed reconciliation'
  Remove-Item -LiteralPath $pendingPath -Force

  # The journal contains only identifiers and hashes, never bearer secrets.
  $source = Get-Content -Raw -LiteralPath $script
  if ($source -notmatch "one_receipt_attested=\\`\$false" -and $source -notmatch 'one_receipt_attested=\\$false') {
    throw 'Local result could be mistaken for an authenticated ONE receipt'
  }
  if ($source -notmatch 'FileMode\\]::CreateNew') { throw 'Pending transaction lacks exclusive creation' }
  # An indirect credential file must not pass the preflight; skip link construction
  # only if this runner account is explicitly denied link privileges.
  $target | ConvertTo-Json | Set-Content -LiteralPath $targetPath -Encoding UTF8
  $indirect = Join-Path $stageState 'original-stage.json'
  Move-Item -LiteralPath $targetPath -Destination $indirect -Force
  try {
    New-Item -ItemType SymbolicLink -Path $targetPath -Target $indirect -ErrorAction Stop | Out-Null
    Assert-Blocked 'Realm cutover refuses reparse-point'
  } catch [System.UnauthorizedAccessException] {
    Write-Host 'realm_transfer_symlink_creation=SKIPPED_NO_PRIVILEGE'
  } finally {
    Remove-Item -LiteralPath $targetPath -Force -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $indirect -Destination $targetPath -Force
  }
  Write-Host 'realm_transfer_preflight_negative=PASS'
} finally {
  $env:LOCALAPPDATA = $oldLocal
  Remove-Item -LiteralPath $temp -Force -Recurse -ErrorAction SilentlyContinue
}

# Expected rejected child processes leave LASTEXITCODE nonzero in the caller.
# The negative assertions above all passed; do not propagate the last reject code.
$global:LASTEXITCODE = 0

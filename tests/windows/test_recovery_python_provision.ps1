$ErrorActionPreference='Stop'
$provisioner = Join-Path $PSScriptRoot '..\..\scripts\windows\install_recovery_python.ps1'
if(-not (Test-Path -LiteralPath $provisioner)) { throw 'missing recovery runtime provisioner' }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temp=Join-Path $env:TEMP ('agentos-recovery-provision-contract-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
  $root=Join-Path $temp 'recovery'
  $archive=Join-Path $temp 'embedded-python.zip'
  $stream=[IO.File]::Open($archive,[IO.FileMode]::CreateNew)
  try {
    $zip=New-Object IO.Compression.ZipArchive($stream,[IO.Compression.ZipArchiveMode]::Create,$false)
    try {
      $entry=$zip.CreateEntry('../outside.txt')
      $writer=New-Object IO.StreamWriter($entry.Open())
      $writer.Write('zip-slip')
      $writer.Dispose()
    } finally { $zip.Dispose() }
  } finally { $stream.Dispose() }
  $digest=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash

  $rejected=$false
  try {
    & $provisioner -RecoveryRoot $root -Archive $archive -ExpectedSha256 ('0'*64) | Out-Null
  } catch {
    $rejected=($_.Exception.Message -match 'RECOVERY_RUNTIME_ARCHIVE_HASH_MISMATCH')
  }
  if(-not $rejected) { throw 'SHA mismatch was not rejected' }
  if(Test-Path (Join-Path $root 'python-runtime')) { throw 'bad hash installed runtime' }

  $rejected=$false
  try {
    & $provisioner -RecoveryRoot $root -Archive $archive -ExpectedSha256 $digest | Out-Null
  } catch {
    $rejected=($_.Exception.Message -match 'RECOVERY_RUNTIME_ARCHIVE_UNSAFE_ENTRY')
  }
  if(-not $rejected) { throw 'zip traversal was not rejected' }
  if(Test-Path (Join-Path $root 'python-runtime')) { throw 'malicious zip installed runtime' }
  if(Test-Path (Join-Path $temp 'outside.txt')) { throw 'zip traversal escaped staging' }

  # Windows file-system names are normally case-insensitive; a ZIP with
  # duplicate effective names must fail before any extraction.
  $duplicateArchive=Join-Path $temp 'duplicate-python.zip'
  $duplicateStream=[IO.File]::Open($duplicateArchive,[IO.FileMode]::CreateNew)
  try {
    $duplicateZip=New-Object IO.Compression.ZipArchive($duplicateStream,[IO.Compression.ZipArchiveMode]::Create,$false)
    try {
      foreach($name in @('python.exe','PYTHON.exe')) {
        $entry=$duplicateZip.CreateEntry($name)
        $writer=New-Object IO.StreamWriter($entry.Open())
        $writer.Write('not-python')
        $writer.Dispose()
      }
    } finally { $duplicateZip.Dispose() }
  } finally { $duplicateStream.Dispose() }
  $duplicateHash=(Get-FileHash -LiteralPath $duplicateArchive -Algorithm SHA256).Hash
  $rejected=$false
  try {
    & $provisioner -RecoveryRoot $root -Archive $duplicateArchive -ExpectedSha256 $duplicateHash | Out-Null
  } catch {
    $rejected=($_.Exception.Message -match 'RECOVERY_RUNTIME_ARCHIVE_DUPLICATE_ENTRY')
  }
  if(-not $rejected) { throw 'case-insensitive duplicate member was not rejected' }
  if(Test-Path (Join-Path $root 'python-runtime')) { throw 'duplicate zip installed runtime' }

  New-Item -ItemType Directory -Path (Join-Path $root 'python-runtime') | Out-Null
  Set-Content -LiteralPath (Join-Path $root 'python-runtime\sentinel.txt') -Value 'protected' -Encoding ASCII
  $rejected=$false
  try {
    & $provisioner -RecoveryRoot $root -Archive $archive -ExpectedSha256 $digest | Out-Null
  } catch {
    $rejected=($_.Exception.Message -match 'RECOVERY_RUNTIME_ALREADY_EXISTS_NEEDS_AUTHORIZED_UPDATE')
  }
  if(-not $rejected) { throw 'existing Recovery runtime was not protected' }
  if(-not (Test-Path -LiteralPath (Join-Path $root 'python-runtime\sentinel.txt'))) {
    throw 'Recovery runtime was modified'
  }
  Write-Host 'recovery_python_fail_closed_windows_contract=PASS'
} finally {
  if(Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}

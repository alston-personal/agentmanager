param(
  [Parameter(Mandatory=$true)][string]$RecoveryRoot,
  [Parameter(Mandatory=$true)][string]$Archive,
  [Parameter(Mandatory=$true)][string]$ExpectedSha256
)
# An authorized *offline*, SHA-pinned CPython Windows embeddable runtime.
# This script never downloads executable code, replaces an established
# Recovery runtime or modifies a registered Scheduled Task.
$ErrorActionPreference='Stop'
if($ExpectedSha256 -cnotmatch '^[0-9a-fA-F]{64}$') {
  throw 'RECOVERY_RUNTIME_SHA256_REQUIRED'
}
$root=[IO.Path]::GetFullPath($RecoveryRoot)
$source=[IO.Path]::GetFullPath($Archive)
if(-not (Test-Path -LiteralPath $source -PathType Leaf)) {
  throw 'RECOVERY_RUNTIME_ARCHIVE_MISSING'
}
if([IO.Path]::GetExtension($source).ToLowerInvariant() -ne '.zip') {
  throw 'RECOVERY_RUNTIME_REQUIRES_PINNED_ZIP'
}
if(-not (Test-Path -LiteralPath $root -PathType Container)) {
  New-Item -ItemType Directory -Path $root -Force | Out-Null
}
$target=Join-Path $root 'python-runtime'
if(Test-Path -LiteralPath $target) {
  throw 'RECOVERY_RUNTIME_ALREADY_EXISTS_NEEDS_AUTHORIZED_UPDATE'
}
$actual=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
if($actual -ne $ExpectedSha256.ToLowerInvariant()) {
  throw 'RECOVERY_RUNTIME_ARCHIVE_HASH_MISMATCH'
}
# Extract only to a new staging directory inside Recovery's own root, never
# into an existing Normal Python installation or the active Recovery slot.
$staging=Join-Path $root ('python-runtime.stage-' + [guid]::NewGuid().ToString('N'))
$created=$false
try {
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip=[IO.Compression.ZipFile]::OpenRead($source)
  try {
    if($zip.Entries.Count -gt 4096) {
      throw 'RECOVERY_RUNTIME_ARCHIVE_ENTRY_LIMIT'
    }
    $totalSize=[long]0
    foreach($entry in $zip.Entries) {
      $totalSize += [long]$entry.Length
      if($totalSize -gt 268435456) {
        throw 'RECOVERY_RUNTIME_ARCHIVE_SIZE_LIMIT'
      }
      # Require a flat official Windows embeddable CPython distribution;
      # no traversal, nested dirs, symlink/mount tricks or arbitrary payload.
      $name=[string]$entry.FullName
      if($name -notmatch '^[A-Za-z0-9_.-]+$' -or
         $name -eq '.' -or $name -eq '..' -or
         $name.EndsWith('.ps1') -or $name.EndsWith('.cmd') -or
         $name.EndsWith('.bat') -or $name.EndsWith('.exe.manifest')) {
        throw 'RECOVERY_RUNTIME_ARCHIVE_UNSAFE_ENTRY'
      }
      $mode=([int]$entry.ExternalAttributes -shr 16) -band 0xF000
      if($mode -eq 0xA000) {
        throw 'RECOVERY_RUNTIME_ARCHIVE_SYMLINK_REJECTED'
      }
    }
  } finally { $zip.Dispose() }
  New-Item -ItemType Directory -Path $staging -ErrorAction Stop | Out-Null
  $created=$true
  Expand-Archive -LiteralPath $source -DestinationPath $staging -ErrorAction Stop
  $python=Join-Path $staging 'python.exe'
  if(-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'RECOVERY_RUNTIME_NO_PYTHON_EXECUTABLE'
  }
  $probeOutput=@(& $python -I -c 'import sys,ssl,urllib.request,json,hashlib; print(sys.version_info.major,sys.prefix)' 2>&1)
  if($LASTEXITCODE -ne 0 -or $probeOutput.Count -eq 0) {
    throw 'RECOVERY_RUNTIME_STANDALONE_PYTHON_INVALID'
  }
  if(Test-Path -LiteralPath $target) {
    throw 'RECOVERY_RUNTIME_CONCURRENT_INSTALL'
  }
  Move-Item -LiteralPath $staging -Destination $target -ErrorAction Stop
  $created=$false
  Write-Output (Join-Path $target 'python.exe')
} finally {
  if($created -and (Test-Path -LiteralPath $staging)) {
    Remove-Item -LiteralPath $staging -Recurse -Force
  }
}

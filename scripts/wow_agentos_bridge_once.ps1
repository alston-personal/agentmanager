# Developer-only one-shot WoW status Bridge.
# No resident process, chat, Node enrollment, or automatic deployment.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$WowRoot,
 [string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",
 [string]$Python='python'
)
$ErrorActionPreference='Stop'
$game=Join-Path $WowRoot '_forever_'
$exe=Join-Path $game 'Wow.exe'
$slot=Join-Path $game 'Interface\AddOns\AgentOSWoW_R001'
$config=Join-Path $InstallRoot 'state\client.json'
$policy=Join-Path $InstallRoot 'state\policy.json'
$source=Join-Path $PSScriptRoot 'capture_wow_status_probe.ps1'
foreach($file in @($exe,$config,$policy,$source)) {
 if(-not (Test-Path -LiteralPath $file -PathType Leaf)) {
   throw 'WOW_BRIDGE_REQUIRED_FILE_MISSING'
 }
 if(((Get-Item -LiteralPath $file -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
   throw 'WOW_BRIDGE_UNSAFE_FILE'
 }
}
foreach($dir in @($WowRoot,$game,(Join-Path $game 'Interface'),(Join-Path $game 'Interface\AddOns'),$slot,$InstallRoot,(Join-Path $InstallRoot 'state'))) {
 if(-not (Test-Path -LiteralPath $dir -PathType Container)) { throw 'WOW_BRIDGE_REQUIRED_DIRECTORY_MISSING' }
 if(((Get-Item -LiteralPath $dir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
   throw 'WOW_BRIDGE_UNSAFE_DIRECTORY'
 }
}
# This is a single bounded status request, not a game automation loop.
# The RGB frame alone confers no authority: the Python host must prove a
# fresh authenticated ONE Node heartbeat before touching the existing slot.
$oldPythonPath=$env:PYTHONPATH
try {
 $agentosCode=Join-Path $InstallRoot 'agentos_node'
 if(-not (Test-Path -LiteralPath $agentosCode -PathType Container)) { throw 'WOW_BRIDGE_NODE_RUNTIME_MISSING' }
 $env:PYTHONPATH=$InstallRoot
 $cells=(& $source -ExpectedExe $exe -Python $Python -OutputCellsJson | Out-String).Trim()
 if(-not $cells -or $cells.Length -gt 4096) { throw 'WOW_BRIDGE_CAPTURE_UNAVAILABLE' }
 $cells | & $Python -m agentos_node.wow_bridge_once $config $policy $slot
 if($LASTEXITCODE -ne 0) { throw 'WOW_BRIDGE_NODE_OR_GAME_VERIFICATION_FAILED' }
 Write-Output 'WOW_BRIDGE_STATUS_REPLY_PUBLISHED_ONCE: reload the game reply slot to view the status; this is not live chat.'
} finally {
 $env:PYTHONPATH=$oldPythonPath
}

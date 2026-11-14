# Passive one-shot Windows RGB status packet capture; no network/ONE actions.
param(
  [string]$Python = "python",
  [string]$TestImage = "",
  [string]$ProcessName = "Wow",
  [string]$ExpectedExe = "",
  [switch]$OutputCellsJson
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class AgentOSWinClientCoord {
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr handle, ref POINT point);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr handle);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][AgentOSWinClientCoord]::SetProcessDPIAware()
$width = 800
$height = 4
$bitmap = $null
try {
 if ($TestImage) {
   $bitmap = [System.Drawing.Bitmap]::FromFile((Resolve-Path -LiteralPath $TestImage).Path)
   if ($bitmap.Width -lt $width -or $bitmap.Height -lt $height) { throw 'capture_image_too_small' }
 } else {
   $matches = @(Get-Process -Name $ProcessName -ErrorAction Stop | Where-Object {
     $_.MainWindowHandle -ne [IntPtr]::Zero -and
     (-not $ExpectedExe -or ($_.Path -and ([IO.Path]::GetFullPath($_.Path) -ieq [IO.Path]::GetFullPath($ExpectedExe))))
   })
   if ($matches.Count -ne 1) { throw 'expected_exactly_one_matching_game_window' }
   $proc = $matches[0]
   if ([AgentOSWinClientCoord]::IsIconic($proc.MainWindowHandle)) { throw 'game_window_minimized' }
   $pt = New-Object AgentOSWinClientCoord+POINT
   if (-not [AgentOSWinClientCoord]::ClientToScreen($proc.MainWindowHandle, [ref]$pt)) { throw 'cannot_locate_game_client_area' }
   $bitmap = New-Object System.Drawing.Bitmap $width, $height
   $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
   try {
     $graphics.CopyFromScreen($pt.X, $pt.Y, 0, 0, $bitmap.Size)
   } finally {
     $graphics.Dispose()
   }
 }
 $cells = New-Object 'System.Collections.Generic.List[int]'
 for ($i = 0; $i -lt 200; $i++) {
   $pixel = $bitmap.GetPixel($i * 4 + 2, 2)
   $v = 0
   if ($pixel.R -ge 128) { $v += 4 }
   if ($pixel.G -ge 128) { $v += 2 }
   if ($pixel.B -ge 128) { $v += 1 }
   $cells.Add($v)
 }
 # The host-only Bridge may consume the raw cells through stdin. No
 # game-origin string ever becomes a shell argument, authority, or token.
 $json = ConvertTo-Json -Compress -InputObject $cells.ToArray()
 if ($OutputCellsJson) {
   Write-Output $json
 } else {
   $json | & $Python -m agentos_node.wow_capture_probe
   if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
 }
} catch {
 Write-Error 'WoW capture unavailable or invalid; no request was dispatched.'
 exit 2
} finally {
 if ($bitmap) { $bitmap.Dispose() }
}

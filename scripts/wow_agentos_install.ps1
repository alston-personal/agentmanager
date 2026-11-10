# AgentOS WoW V1 local addon installer (candidate; no Node enrollment or Bridge service)
[CmdletBinding()]
param(
 [ValidateSet('Install','Uninstall')][string]$Mode='Install',
 [Parameter(Mandatory=$true)][string]$WowRoot,
 [string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",
 [string]$OneUrl='https://studio.milkcat.org/dashboard/api/agentos',
 [string]$TargetRealmId='',
 [switch]$ConfirmInstall
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$addonNames=@('AgentOSWoW','AgentOSWoW_R001')
$sourceRoot=Join-Path (Split-Path -Parent $PSScriptRoot) 'integrations\wow'
$preflight=Join-Path $PSScriptRoot 'wow_agentos_installer_preflight.ps1'
function Stop-Install([string]$Reason) { throw "AGENTOS_WOW_INSTALLER: $Reason" }
function Get-SafeDirectory([string]$Folder) {
 if(-not (Test-Path -LiteralPath $Folder -PathType Container)){Stop-Install 'GAME_PATH_NOT_FOUND'}
 $item=Get-Item -LiteralPath $Folder -Force
 if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){Stop-Install 'REPARSE_GAME_PATH'}
 return $item.FullName
}
function Assert-RegularFile([string]$File) {
 $item=Get-Item -LiteralPath $File -Force -ErrorAction Stop
 if($item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){
   Stop-Install 'UNSAFE_FILE'
 }
}
# Never infer the game path from a network value or write into the Node state.
$root=Get-SafeDirectory $WowRoot
$game=Join-Path $root '_forever_'
$exe=Join-Path $game 'Wow.exe'
if(-not (Test-Path -LiteralPath $exe -PathType Leaf)){Stop-Install 'FOREVER_CLIENT_REQUIRED'}
Assert-RegularFile $exe
$interface=Join-Path $game 'Interface'
$addons=Join-Path $interface 'AddOns'
Get-SafeDirectory $game | Out-Null
Get-SafeDirectory $interface | Out-Null
Get-SafeDirectory $addons | Out-Null
if(Get-Process -Name 'Wow' -ErrorAction SilentlyContinue){
 Stop-Install 'CLOSE_WOW_BEFORE_CHANGING_ADDONS'
}
$targets=@{}
foreach($name in $addonNames){
 $targets[$name]=Join-Path $addons $name
 if($Mode -eq 'Install'){
   $src=Join-Path $sourceRoot $name
   Get-SafeDirectory $src | Out-Null
   foreach($file in @(Get-ChildItem -LiteralPath $src -File -Force)){
     Assert-RegularFile $file.FullName
     if($file.Extension -notin @('.toc','.lua')){Stop-Install 'UNSUPPORTED_SOURCE_FILE'}
   }
 }
}
if($Mode -eq 'Install'){
 if(-not (Test-Path -LiteralPath $preflight -PathType Leaf)){Stop-Install 'PREFLIGHT_MISSING'}
 $raw=& $preflight -WowRoot $root -InstallRoot $InstallRoot -OneUrl $OneUrl -TargetRealmId $TargetRealmId -Json | Out-String
 try {$result=$raw | ConvertFrom-Json} catch {Stop-Install 'PREFLIGHT_INVALID'}
 if($result.state -ne 'NODE_VERIFIED' -or $result.wow_client -ne 'forever'){Stop-Install ('PREFLIGHT_'+[string]$result.state)}
 foreach($name in $addonNames){
   if(Test-Path -LiteralPath $targets[$name]){Stop-Install 'ADDON_ALREADY_EXISTS'}
 }
 if(-not $ConfirmInstall){
   $approval=Read-Host 'Install the two offline AgentOS WoW Addons? Type INSTALL'
   if($approval -cne 'INSTALL'){Stop-Install 'NOT_APPROVED'}
 }
 $staged=New-Object System.Collections.Generic.List[string]
 $installed=New-Object System.Collections.Generic.List[string]
 try{
   foreach($name in $addonNames){
     $stage=Join-Path $addons ('.agentos-wow-stage-'+[guid]::NewGuid().ToString('N'))
     $staged.Add($stage)
     New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
     $src=Join-Path $sourceRoot $name
     $files=@(Get-ChildItem -LiteralPath $src -File)
     foreach($file in $files){
       $destination=Join-Path $stage $file.Name
       Copy-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
       if((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
          (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash){
         Stop-Install 'COPY_HASH_MISMATCH'
       }
     }
   }
   for($i=0; $i -lt $addonNames.Count; $i++){
     $name=$addonNames[$i]
     Move-Item -LiteralPath $staged[$i] -Destination $targets[$name] -ErrorAction Stop
     $installed.Add($targets[$name])
   }
 }catch{
   # Only remove directories this invocation created. No overwrites.
   foreach($dir in $installed){if(Test-Path -LiteralPath $dir){Remove-Item -LiteralPath $dir -Recurse -Force}}
   foreach($dir in $staged){if(Test-Path -LiteralPath $dir){Remove-Item -LiteralPath $dir -Recurse -Force}}
   throw
 }
 Write-Output 'ADDONS_INSTALLED_OFFLINE: open WoW, type /agentos; Bridge and ONE remain unverified.'
 exit 0
}
# Uninstall: refuse to delete altered files or unknown user content.
if(-not $ConfirmInstall){
 $approval=Read-Host 'Remove the two AgentOS WoW addon folders? Type UNINSTALL'
 if($approval -cne 'UNINSTALL'){Stop-Install 'NOT_APPROVED'}
}
foreach($name in $addonNames){
 $target=$targets[$name]
 if(-not (Test-Path -LiteralPath $target)){continue}
 Get-SafeDirectory $target | Out-Null
 $src=Join-Path $sourceRoot $name
 $expected=@(Get-ChildItem -LiteralPath $src -File | ForEach-Object {$_.Name} | Sort-Object)
 $actual=@(Get-ChildItem -LiteralPath $target -Force)
 if(@($actual | Where-Object {$_.PSIsContainer}).Count -gt 0 -or
    @($actual | ForEach-Object {$_.Name} | Sort-Object) -join '|' -cne ($expected -join '|')){
    Stop-Install 'ADDON_MODIFIED_REFUSE_UNINSTALL'
 }
 foreach($file in $actual){
   Assert-RegularFile $file.FullName
   $original=Join-Path $src $file.Name
   if((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne
      (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash){
     Stop-Install 'ADDON_CONTENT_CHANGED_REFUSE_UNINSTALL'
   }
 }
}
foreach($name in $addonNames){
 if(Test-Path -LiteralPath $targets[$name]){Remove-Item -LiteralPath $targets[$name] -Recurse -Force}
}
Write-Output 'ADDONS_UNINSTALLED: existing AgentOS Node and Realm untouched.'

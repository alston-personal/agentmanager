# Return only a verified WoW: Forever installation root (not an arbitrary folder).
[CmdletBinding()]
param(
 [string]$WowRoot='',
 [string[]]$CandidateRoots=@(),
 [switch]$NoFolderPicker
)
$ErrorActionPreference='Stop'
function Test-ForeverRoot([string]$Root){
 if(-not $Root){return $false}
 try {
  $rootItem=Get-Item -LiteralPath $Root -ErrorAction Stop
  if(-not $rootItem.PSIsContainer -or
     (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){return $false}
  $sub=Join-Path $rootItem.FullName '_forever_'
  $client=Join-Path $sub 'Wow.exe'
  if(-not (Test-Path -LiteralPath $client -PathType Leaf)){return $false}
  foreach($dir in @($sub,(Join-Path $sub 'Interface'),(Join-Path $sub 'Interface\AddOns'))){
   $item=Get-Item -LiteralPath $dir -ErrorAction Stop
   if(-not $item.PSIsContainer -or
      (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)){return $false}
  }
  $exe=Get-Item -LiteralPath $client -ErrorAction Stop
  if(($exe.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){return $false}
  return $true
 }catch{return $false}
}
$roots=New-Object System.Collections.Generic.List[string]
if($WowRoot){$roots.Add($WowRoot)}
foreach($candidate in $CandidateRoots){if($candidate){$roots.Add($candidate)}}
foreach($prefix in @($env:ProgramFiles,${env:ProgramFiles(x86)},$env:ProgramW6432,'C:\Games','D:\Games','D:\')){
 if($prefix){$roots.Add((Join-Path $prefix 'World of Warcraft'))}
}
foreach($root in $roots){
 if(Test-ForeverRoot $root){
  (Get-Item -LiteralPath $root).FullName
  exit 0
 }
}
if($NoFolderPicker){exit 2}
try{
 Add-Type -AssemblyName System.Windows.Forms
 $dialog=New-Object System.Windows.Forms.FolderBrowserDialog
 $dialog.Description='Select the World of Warcraft folder containing _forever_'
 $dialog.ShowNewFolderButton=$false
 if($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){
  if(Test-ForeverRoot $dialog.SelectedPath){
   (Get-Item -LiteralPath $dialog.SelectedPath).FullName
   exit 0
  }
 }
}catch{}
exit 2

# WoW AgentOS installer preflight (no game/Realm mutations)
param(
 [string]$OneUrl = 'https://studio.milkcat.org/dashboard/api/agentos',
 [string]$TargetRealmId = '',
 [string]$WowRoot = '',
 [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
 [switch]$Json
)
$ErrorActionPreference='Stop'
function Find-Game {
 param([string]$Requested)
 $candidates=@()
 if($Requested){$candidates+= $Requested}
 if($env:ProgramFiles){$candidates+=(Join-Path $env:ProgramFiles 'World of Warcraft')}
 foreach($root in ($candidates | Select-Object -Unique)){
   if(-not (Test-Path -LiteralPath $root -PathType Container)){continue}
   if(Test-Path -LiteralPath (Join-Path $root '_forever_\Wow.exe') -PathType Leaf){return @{client='forever';root=$root}}
   if(Test-Path -LiteralPath (Join-Path $root '_retail_\Wow.exe') -PathType Leaf){return @{client='retail_unverified';root=$root}}
   foreach($sub in @('_classic_','_classic_era_')){
     if(Test-Path -LiteralPath (Join-Path $root "$sub\Wow.exe") -PathType Leaf){return @{client='classic_unverified';root=$root}}
   }
 }
 return @{client='not_detected';root=$null}
}
$game=Find-Game $WowRoot
$out=[ordered]@{
 schema='agentos.wow-installer-preflight/v1'
 state='PREFLIGHT_ERROR'
 node_installed=$false
 node_id=$null
 realm_id=$null
 one_url=$null
 wow_client=$game.client
 wow_root=$game.root
 addon_installed=$false
 needs_join=$false
}
try{
 $uri=[uri]$OneUrl
 if(-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'https'){throw 'HTTPS_REQUIRED'}
 $config=Join-Path $InstallRoot 'state\client.json'
 $launcher=Join-Path $InstallRoot 'agentos-client.cmd'
 if(-not (Test-Path -LiteralPath $config -PathType Leaf)){
   if(Test-Path -LiteralPath $launcher -PathType Leaf){$out.state='NODE_UNENROLLED';$out.node_installed=$true}
   else{$out.state='NODE_NOT_INSTALLED'}
   $out.needs_join=$true
 }else{
   $cfg=Get-Content -Raw -LiteralPath $config | ConvertFrom-Json
   $out.node_installed=$true
   $out.node_id=[string]$cfg.node_id
   $out.realm_id=[string]$cfg.realm_id
   $out.one_url=([string]$cfg.one_url).TrimEnd('/')
   if(-not $cfg.node_token -or -not $out.realm_id -or -not $out.one_url){
     $out.state='NODE_AUTH_INVALID'
   }elseif($out.one_url -ne $OneUrl.TrimEnd('/') -or ($TargetRealmId -and $out.realm_id -ne $TargetRealmId)){
     $out.state='CROSS_REALM_UNAVAILABLE'
   }elseif(-not (Test-Path -LiteralPath $launcher -PathType Leaf)){
     $out.state='NODE_UNAVAILABLE'
   }else{
     # No stdout: do not expose sensitive status data.
     & $launcher verify 1>$null 2>$null
     if($LASTEXITCODE -eq 0){$out.state='NODE_VERIFIED'}else{$out.state='NODE_UNAVAILABLE'}
   }
 }
 if($out.state -eq 'NODE_VERIFIED' -and $game.client -ne 'forever'){$out.state='WOW_CLIENT_UNSUPPORTED'}
}catch{
 $out.state='PREFLIGHT_ERROR'
}
if($Json){$out | ConvertTo-Json -Depth 4}else{
 Write-Host 'AgentOS WoW installation preflight (read-only)'
 Write-Host ('Result: '+$out.state)
 Write-Host ('Game client: '+$out.wow_client)
 if($out.realm_id){Write-Host ('Existing Realm: '+$out.realm_id)}
 Write-Host 'No Node credentials or game files have been modified.'
}

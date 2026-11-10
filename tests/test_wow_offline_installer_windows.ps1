# Windows CI-only functional test. No real WoW or ONE credentials used.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=Split-Path -Parent $PSScriptRoot
if($env:WOW_INSTALLER_ROOT){$repo=$env:WOW_INSTALLER_ROOT}
$installer=Join-Path $repo 'scripts\wow_agentos_install.ps1'
$temp=Join-Path ([IO.Path]::GetTempPath()) ('wow-installer-ci-'+[guid]::NewGuid().ToString('N'))
$gameRoot=Join-Path $temp 'World of Warcraft'
$installRoot=Join-Path $temp 'AgentOS'
$addonRoot=Join-Path $gameRoot '_forever_\Interface\AddOns'
function Assert-True($Condition,$Message){if(-not $Condition){throw "WINDOWS_WOW_INSTALLER_TEST: $Message"}}
try{
 New-Item -ItemType Directory -Force -Path $addonRoot | Out-Null
 New-Item -ItemType Directory -Force -Path (Join-Path $installRoot 'state') | Out-Null
 [IO.File]::WriteAllBytes((Join-Path $gameRoot '_forever_\Wow.exe'),[byte[]](0,1,2))
 $url='https://studio.milkcat.org/dashboard/api/agentos'
 $config=@{node_id='mock-node';realm_id='mock-realm';one_url=$url;node_token='ci-mock-not-real'} | ConvertTo-Json
 Set-Content -LiteralPath (Join-Path $installRoot 'state\client.json') -Value $config
 Set-Content -LiteralPath (Join-Path $installRoot 'agentos-client.cmd') -Encoding Ascii -Value '@echo off','exit /b 0'
 & $installer -Mode Install -WowRoot $gameRoot -InstallRoot $installRoot -OneUrl $url -TargetRealmId 'mock-realm' -ConfirmInstall
 Assert-True (Test-Path (Join-Path $addonRoot 'AgentOSWoW\AgentOSWoW.lua')) 'missing main addon'
 Assert-True (Test-Path (Join-Path $addonRoot 'AgentOSWoW_R001\Reply.lua')) 'missing reply slot'
 $wasRejected=$false
 try{& $installer -Mode Install -WowRoot $gameRoot -InstallRoot $installRoot -OneUrl $url -TargetRealmId 'mock-realm' -ConfirmInstall}catch{$wasRejected=($_.Exception.Message -like '*ADDON_ALREADY_EXISTS*')}
 Assert-True $wasRejected 'existing addon should never be overwritten'
 & $installer -Mode Uninstall -WowRoot $gameRoot -InstallRoot $installRoot -ConfirmInstall
 Assert-True (-not (Test-Path (Join-Path $addonRoot 'AgentOSWoW'))) 'uninstall did not remove main addon'
 Assert-True (-not (Test-Path (Join-Path $addonRoot 'AgentOSWoW_R001'))) 'uninstall did not remove reply addon'
 Assert-True (Test-Path (Join-Path $installRoot 'state\client.json')) 'Node configuration was modified'
 & $installer -Mode Install -WowRoot $gameRoot -InstallRoot $installRoot -OneUrl $url -TargetRealmId 'mock-realm' -ConfirmInstall
 Add-Content -LiteralPath (Join-Path $addonRoot 'AgentOSWoW\AgentOSWoW.lua') -Value '-- custom local content'
 $wasRejected=$false
 try{& $installer -Mode Uninstall -WowRoot $gameRoot -InstallRoot $installRoot -ConfirmInstall}catch{$wasRejected=($_.Exception.Message -like '*ADDON_CONTENT_CHANGED_REFUSE_UNINSTALL*')}
 Assert-True $wasRejected 'modified addon content must be preserved'
 Assert-True (Test-Path (Join-Path $addonRoot 'AgentOSWoW\AgentOSWoW.lua')) 'modified content was lost'
 Write-Output 'WINDOWS_WOW_OFFLINE_INSTALLER=PASS'
}finally{
 if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Recurse -Force}
}

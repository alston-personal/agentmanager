param([Parameter(Mandatory=$true)][string]$SourceCommit,[string]$Repo='alston-personal/agentmanager',[string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",[string]$TaskName='AgentOS Thin Client')
$ErrorActionPreference='Stop'
if($SourceCommit -notmatch '^[0-9a-f]{40}$'){throw 'SourceCommit must be immutable SHA'}
$versions=Join-Path $InstallRoot 'versions'; $candidate=Join-Path $versions $SourceCommit
$currentFile=Join-Path $InstallRoot 'current.json'; $lkgFile=Join-Path $InstallRoot 'last-known-good.json'
$tmpRepo=Join-Path $env:TEMP ("agentos-"+$SourceCommit+"-git")
Remove-Item -Recurse -Force $tmpRepo -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $tmpRepo|Out-Null
& git -C $tmpRepo init -q
if($LASTEXITCODE -ne 0){throw 'candidate git init failed'}
& git -C $tmpRepo remote add origin ("https://github.com/"+$Repo+".git")
& git -C $tmpRepo config core.sparseCheckout true
$infoDir=Join-Path $tmpRepo '.git\info'
New-Item -ItemType Directory -Force -Path $infoDir|Out-Null
"agentos_node/"|Set-Content -Encoding ASCII (Join-Path $infoDir 'sparse-checkout')
& git -C $tmpRepo fetch -q --depth 1 --filter=blob:none origin $SourceCommit
if($LASTEXITCODE -ne 0){throw 'candidate immutable fetch failed'}
$resolved=(& git -C $tmpRepo rev-parse FETCH_HEAD).Trim()
if($resolved -ne $SourceCommit){throw 'candidate fetched commit does not match requested source commit'}
& git -C $tmpRepo checkout -q FETCH_HEAD
if($LASTEXITCODE -ne 0){throw 'candidate sparse checkout failed'}
$sourcePkg=Join-Path $tmpRepo 'agentos_node'
if(-not(Test-Path $sourcePkg)){throw 'candidate sparse checkout missing agentos_node package'}
Remove-Item -Recurse -Force $candidate -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $candidate|Out-Null
Copy-Item -Recurse -Force $sourcePkg (Join-Path $candidate 'agentos_node')
$manifest=@(Get-ChildItem -LiteralPath (Join-Path $candidate 'agentos_node') -Recurse -File | Sort-Object FullName | ForEach-Object {
  [ordered]@{path=$_.FullName.Substring($candidate.Length+1);sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant();bytes=$_.Length}
})
$manifestRecord=[ordered]@{schema='agentos.runtime-package-manifest/v0.1';source_commit=$SourceCommit;files=$manifest}
$manifestRecord|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 (Join-Path $candidate 'package-manifest.json')
Remove-Item -Recurse -Force $tmpRepo -ErrorAction SilentlyContinue
$env:PYTHONPATH=$candidate
& python -c "import agentos_node.thin_client,agentos_node.interactive_desktop,agentos_node.client_cli; print('candidate_import=PASS')"
if($LASTEXITCODE -ne 0){Remove-Item -Recurse -Force $candidate;throw 'candidate import validation failed'}
$previous=$null
if(Test-Path $currentFile){
  $previous=Get-Content -Raw $currentFile|ConvertFrom-Json
}else{
  $legacyId='legacy-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
  $legacy=Join-Path $versions $legacyId
  New-Item -ItemType Directory -Force -Path $legacy|Out-Null
  $legacyPkg=Join-Path $legacy 'agentos_node'
  if(-not(Test-Path (Join-Path $InstallRoot 'agentos_node'))){throw 'cannot bootstrap LKG: active agentos_node missing'}
  Copy-Item -Recurse -Force (Join-Path $InstallRoot 'agentos_node') $legacyPkg
  $legacyCommit='unknown'
  $legacyProv=Join-Path $InstallRoot 'runtime-provenance.json'
  if(Test-Path $legacyProv){
    try{$legacyCommit=[string]((Get-Content -Raw $legacyProv|ConvertFrom-Json).source_commit)}catch{}
  }
  $previous=[ordered]@{schema='agentos.thin-client-runtime/v0.1';source_ref='bootstrap-lkg';source_commit=$legacyCommit;path=$legacy;installed_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');status='active-accepted'}
  $previous|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 (Join-Path $legacy 'runtime-provenance.json')
  $previous|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $currentFile
}
$previous|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $lkgFile
$launcher=Join-Path $InstallRoot 'agentos-client.cmd';$next=Join-Path $InstallRoot 'agentos-client.next.cmd';$state=Join-Path $InstallRoot 'state'
$lines=@('@echo off','set "PYTHONPATH='+$candidate+'"','set "AGENTOS_CLIENT_HOME='+$state+'"','set "AGENTOS_RUNTIME_PROVENANCE='+(Join-Path $candidate 'runtime-provenance.json')+'"','python -m agentos_node.client_cli %*')
$lines|Set-Content -Encoding ASCII $next
$record=[ordered]@{schema='agentos.thin-client-runtime/v0.1';source_ref='core/integration';source_commit=$SourceCommit;path=$candidate;installed_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');status='candidate-validated'}
$record|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 (Join-Path $candidate 'runtime-provenance.json')
Move-Item -Force $next $launcher
$record.status='awaiting-controller-acceptance'
$record.rollback_deadline=(Get-Date).ToUniversalTime().AddMinutes(3).ToString('yyyy-MM-ddTHH:mm:ssZ')
$guardUrl="https://raw.githubusercontent.com/$Repo/$SourceCommit/scripts/windows/transactional_ota_guard.ps1"
$finalizeUrl="https://raw.githubusercontent.com/$Repo/$SourceCommit/scripts/windows/transactional_ota_finalize.ps1"
Invoke-WebRequest -UseBasicParsing -Uri $guardUrl -OutFile (Join-Path $InstallRoot 'transactional_ota_guard.ps1')
Invoke-WebRequest -UseBasicParsing -Uri $finalizeUrl -OutFile (Join-Path $InstallRoot 'transactional_ota_finalize.ps1')
$guardTask='AgentOS Thin Client OTA Guard'
$guardAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "'+(Join-Path $InstallRoot 'transactional_ota_guard.ps1')+'"')
$guardTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(4)
Register-ScheduledTask -TaskName $guardTask -Action $guardAction -Trigger $guardTrigger -Force | Out-Null
$record|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $currentFile
$restart="Start-Sleep -Seconds 8; Stop-ScheduledTask -TaskName '$TaskName' -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1; Start-ScheduledTask -TaskName '$TaskName'"
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-NonInteractive','-Command',$restart)
Write-Output 'agentos_ota_stage=ACTIVATING'
Write-Output ('agentos_ota_candidate='+$SourceCommit)
Write-Output 'agentos_ota_controller_acceptance=PENDING'

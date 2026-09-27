param([Parameter(Mandatory=$true)][string]$SourceCommit,[string]$Repo='alston-personal/agentmanager',[string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",[string]$TaskName='AgentOS Thin Client')
$ErrorActionPreference='Stop'
if($SourceCommit -notmatch '^[0-9a-f]{40}$'){throw 'SourceCommit must be immutable SHA'}
$versions=Join-Path $InstallRoot 'versions'; $candidate=Join-Path $versions $SourceCommit
$currentFile=Join-Path $InstallRoot 'current.json'; $lkgFile=Join-Path $InstallRoot 'last-known-good.json'
New-Item -ItemType Directory -Force -Path $candidate|Out-Null
$files=@('agentos_node/__init__.py','agentos_node/thin_client.py','agentos_node/runtime_provenance.py','agentos_node/interactive_desktop.py','agentos_node/thin_client_transport.py','agentos_node/client_cli.py','agentos_node/agent_surfaces.py','agentos_node/session_bridge.py','agentos_node/onboarding.py')
$base="https://raw.githubusercontent.com/$Repo/$SourceCommit"
foreach($rel in $files){$dest=Join-Path $candidate ($rel -replace '/','\');New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent)|Out-Null;Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri "$base/$rel" -OutFile $dest}
$env:PYTHONPATH=$candidate
& python -c "import agentos_node.thin_client,agentos_node.interactive_desktop,agentos_node.client_cli; print('candidate_import=PASS')"
if($LASTEXITCODE -ne 0){Remove-Item -Recurse -Force $candidate;throw 'candidate import validation failed'}
$previous=$null;if(Test-Path $currentFile){$previous=Get-Content -Raw $currentFile|ConvertFrom-Json}
if($previous){$previous|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $lkgFile}
$launcher=Join-Path $InstallRoot 'agentos-client.cmd';$next=Join-Path $InstallRoot 'agentos-client.next.cmd';$state=Join-Path $InstallRoot 'state'
$lines=@('@echo off','set "PYTHONPATH='+$candidate+'"','set "AGENTOS_CLIENT_HOME='+$state+'"','python -m agentos_node.client_cli %*')
$lines|Set-Content -Encoding ASCII $next
$record=[ordered]@{schema='agentos.thin-client-runtime/v0.1';source_ref='core/integration';source_commit=$SourceCommit;path=$candidate;installed_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');status='candidate-validated'}
$record|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 (Join-Path $candidate 'runtime-provenance.json')
Move-Item -Force $next $launcher
$record.status='activating';$record|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $currentFile
Start-ScheduledTask -TaskName $TaskName
Write-Output 'agentos_ota_stage=ACTIVATING'
Write-Output ('agentos_ota_candidate='+$SourceCommit)

Start-Sleep -Seconds 12
$task=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$healthy=$false
if($task -and $task.State -eq 'Running'){$healthy=$true}
if(-not $healthy){
  if($previous -and $previous.path){
    $rollbackLines=@('@echo off','set "PYTHONPATH='+[string]$previous.path+'"','set "AGENTOS_CLIENT_HOME='+$state+'"','python -m agentos_node.client_cli %*')
    $rollbackNext=Join-Path $InstallRoot 'agentos-client.rollback.cmd'
    $rollbackLines|Set-Content -Encoding ASCII $rollbackNext
    Move-Item -Force $rollbackNext $launcher
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $TaskName
    $previous.status='rollback-restored'
    $previous|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $currentFile
    Write-Output 'agentos_ota_rollback=PASS'
  }
  throw 'candidate post-switch health acceptance failed'
}
$record.status='active-accepted'
$record.accepted_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$record|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $currentFile
$record|ConvertTo-Json -Depth 5|Set-Content -Encoding UTF8 $lkgFile
Write-Output 'agentos_ota_post_switch=PASS'
Write-Output 'agentos_ota=PASS'

param([Parameter(Mandatory=$true)][ValidateSet('accept','rollback')][string]$Action,[string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",[string]$TaskName='AgentOS Thin Client')
$ErrorActionPreference='Stop'
function Write-JsonAtomic([object]$Value,[string]$Path,[int]$Depth=8){
  $json=$Value|ConvertTo-Json -Depth $Depth
  $enc=New-Object System.Text.UTF8Encoding($false)
  for($i=0;$i -lt 10;$i++){
    $tmp=$Path+'.tmp.'+[guid]::NewGuid().ToString('N')
    try{
      [System.IO.File]::WriteAllText($tmp,$json+[Environment]::NewLine,$enc)
      if(Test-Path $Path){$bak=$Path+'.bak'; Remove-Item -Force $bak -ErrorAction SilentlyContinue; [System.IO.File]::Replace($tmp,$Path,$bak); Remove-Item -Force $bak -ErrorAction SilentlyContinue}else{[System.IO.File]::Move($tmp,$Path)}
      return
    }catch{
      Remove-Item -Force $tmp -ErrorAction SilentlyContinue
      if($i -eq 9){throw}
      Start-Sleep -Milliseconds ([Math]::Min(1500,100*($i+1)))
    }
  }
}
$currentFile=Join-Path $InstallRoot 'current.json'
$lkgFile=Join-Path $InstallRoot 'last-known-good.json'
$launcher=Join-Path $InstallRoot 'agentos-client.cmd'
$state=Join-Path $InstallRoot 'state'
if(-not(Test-Path $currentFile)){throw 'current runtime record missing'}
$current=Get-Content -Raw $currentFile|ConvertFrom-Json
if($Action -eq 'accept'){
  if($current.status -ne 'awaiting-controller-acceptance'){throw 'runtime is not awaiting acceptance'}
  $current.status='active-accepted'
  $current|Add-Member -NotePropertyName accepted_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) -Force
  Write-JsonAtomic $current $currentFile 8
  Write-JsonAtomic $current $lkgFile 8
  Write-Output 'agentos_ota_finalize=PASS'
  exit 0
}
if(-not(Test-Path $lkgFile)){throw 'last-known-good runtime missing'}
$lkg=Get-Content -Raw $lkgFile|ConvertFrom-Json
if(-not $lkg.path){throw 'last-known-good path missing'}
$next=Join-Path $InstallRoot 'agentos-client.rollback.cmd'
@('@echo off','set "PYTHONPATH='+[string]$lkg.path+'"','set "AGENTOS_CLIENT_HOME='+$state+'"','set "AGENTOS_RUNTIME_PROVENANCE='+(Join-Path ([string]$lkg.path) 'runtime-provenance.json')+'"','python -m agentos_node.client_cli %*')|Set-Content -Encoding ASCII $next
Move-Item -Force $next $launcher
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $TaskName
$lkg.status='rollback-restored'
$lkg|Add-Member -NotePropertyName rolled_back_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) -Force
Write-JsonAtomic $lkg $currentFile 8
Write-Output 'agentos_ota_rollback=PASS'

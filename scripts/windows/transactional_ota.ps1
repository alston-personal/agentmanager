param([Parameter(Mandatory=$true)][string]$SourceCommit,[string]$ToolCommit=$SourceCommit,[string]$Repo='alston-personal/agentmanager',[string]$InstallRoot="$env:LOCALAPPDATA\AgentOS",[string]$TaskName='AgentOS Thin Client')
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
if($SourceCommit -notmatch '^[0-9a-f]{40}$'){throw 'SourceCommit must be immutable SHA'}
if($ToolCommit -notmatch '^[0-9a-f]{40}$'){throw 'ToolCommit must be immutable SHA'}
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
@("agentos_node/","agent_core/")|Set-Content -Encoding ASCII (Join-Path $infoDir 'sparse-checkout')
& git -C $tmpRepo fetch -q --depth 1 --filter=blob:none origin $SourceCommit
if($LASTEXITCODE -ne 0){throw 'candidate immutable fetch failed'}
$resolved=(& git -C $tmpRepo rev-parse FETCH_HEAD).Trim()
if($resolved -ne $SourceCommit){throw 'candidate fetched commit does not match requested source commit'}
& git -C $tmpRepo checkout -q FETCH_HEAD
if($LASTEXITCODE -ne 0){throw 'candidate sparse checkout failed'}
$sourcePkg=Join-Path $tmpRepo 'agentos_node'
$sourceCore=Join-Path $tmpRepo 'agent_core'
if(-not(Test-Path $sourcePkg)){throw 'candidate sparse checkout missing agentos_node package'}
if(-not(Test-Path $sourceCore)){throw 'candidate sparse checkout missing agent_core package'}
Remove-Item -Recurse -Force $candidate -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $candidate|Out-Null
Copy-Item -Recurse -Force $sourcePkg (Join-Path $candidate 'agentos_node')
Copy-Item -Recurse -Force $sourceCore (Join-Path $candidate 'agent_core')
$manifest=@(Get-ChildItem -LiteralPath $candidate -Recurse -File | Sort-Object FullName | ForEach-Object {
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
  Write-JsonAtomic $previous (Join-Path $legacy 'runtime-provenance.json')
  Write-JsonAtomic $previous $currentFile
}
Write-JsonAtomic $previous $lkgFile
$launcher=Join-Path $InstallRoot 'agentos-client.cmd';$next=Join-Path $InstallRoot 'agentos-client.next.cmd';$state=Join-Path $InstallRoot 'state'
$lines=@(
  '@echo off'
  ('set "PYTHONPATH={0}"' -f [string]$candidate)
  ('set "AGENTOS_CLIENT_HOME={0}"' -f [string]$state)
  ('set "AGENTOS_RUNTIME_PROVENANCE={0}"' -f [string](Join-Path $candidate 'runtime-provenance.json'))
  'python -m agentos_node.client_cli %*'
)
$lines|Set-Content -Encoding ASCII $next
$launcherCheck=Get-Content -Raw $next
if($launcherCheck -notmatch '(?m)^set "PYTHONPATH=[A-Za-z]:\\'){throw 'candidate launcher validation failed: PYTHONPATH'}
if($launcherCheck -notmatch '(?m)^set "AGENTOS_RUNTIME_PROVENANCE=[A-Za-z]:\\'){throw 'candidate launcher validation failed: provenance'}
$record=[ordered]@{schema='agentos.thin-client-runtime/v0.1';source_ref='core/integration';source_commit=$SourceCommit;path=$candidate;installed_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');status='candidate-validated'}
Write-JsonAtomic $record (Join-Path $candidate 'runtime-provenance.json')
$record.status='awaiting-controller-acceptance'
$record.rollback_deadline=(Get-Date).ToUniversalTime().AddMinutes(3).ToString('yyyy-MM-ddTHH:mm:ssZ')

# One-click runtimes register the Thin Client task against a version-specific
# supervisor. Convert that existing, already-approved supervisor carrier into a
# current.json-driven loader so transactional OTA can actually switch runtime
# generations without changing the task's execution surface.
$registeredTask=Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$registeredAction=$registeredTask.Actions|Select-Object -First 1
if([string]$registeredAction.Execute -notmatch '(?i)powershell\.exe$guardUrl="https://raw.githubusercontent.com/$Repo/$ToolCommit/scripts/windows/transactional_ota_guard.ps1"
$finalizeUrl="https://raw.githubusercontent.com/$Repo/$ToolCommit/scripts/windows/transactional_ota_finalize.ps1"
$guardPath=Join-Path $InstallRoot ("transactional_ota_guard-"+$SourceCommit+".ps1")
$finalizePath=Join-Path $InstallRoot ("transactional_ota_finalize-"+$SourceCommit+".ps1")
Invoke-WebRequest -UseBasicParsing -Uri $guardUrl -OutFile $guardPath
Invoke-WebRequest -UseBasicParsing -Uri $finalizeUrl -OutFile $finalizePath
$record|Add-Member -NotePropertyName guard_helper -NotePropertyValue $guardPath -Force
$record|Add-Member -NotePropertyName finalize_helper -NotePropertyValue $finalizePath -Force
$guardTask='AgentOS Thin Client OTA Guard'
$helperPrincipal=New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
$helperSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$guardAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$guardPath+'" -InstallRoot "'+$InstallRoot+'"')
$guardTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(4)
Register-ScheduledTask -TaskName $guardTask -Action $guardAction -Trigger $guardTrigger -Settings $helperSettings -Principal $helperPrincipal -Force | Out-Null
Write-JsonAtomic $record $currentFile
Move-Item -Force $next $launcher
$activatorTask='AgentOS Thin Client OTA Activator'
$activatorScript=Join-Path $InstallRoot ("transactional_ota_activate-"+$SourceCommit+".ps1")
@(
  "param([string]`$TaskName='AgentOS Thin Client')",
  "`$ErrorActionPreference='Stop'",
  "Stop-ScheduledTask -TaskName `$TaskName -ErrorAction SilentlyContinue",
  "Start-Sleep -Seconds 2",
  "`$clients=@(Get-CimInstance Win32_Process | Where-Object { `$_.Name -match '^pythonw?\.exe$' -and `$_.CommandLine -match '(?i)-m\s+agentos_node\.client_cli\s+run(?:\s|$)' })",
  "foreach(`$client in `$clients){ Stop-Process -Id `$client.ProcessId -Force -ErrorAction SilentlyContinue }",
  "for(`$i=0;`$i -lt 20;`$i++){ `$remaining=@(Get-CimInstance Win32_Process | Where-Object { `$_.Name -match '^pythonw?\.exe$' -and `$_.CommandLine -match '(?i)-m\s+agentos_node\.client_cli\s+run(?:\s|$)' }); if(`$remaining.Count -eq 0){break}; Start-Sleep -Milliseconds 500 }",
  "Start-ScheduledTask -TaskName `$TaskName",
  "Start-Sleep -Seconds 3",
  "`$task=Get-ScheduledTask -TaskName `$TaskName -ErrorAction Stop",
  "if([string]`$task.State -ne 'Running'){ throw 'Thin Client scheduled task did not enter Running state' }",
  "Write-Output 'agentos_ota_activator=PASS'"
)|Set-Content -Encoding ASCII $activatorScript
$record|Add-Member -NotePropertyName activator_helper -NotePropertyValue $activatorScript -Force
$activatorAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$activatorScript+'" -TaskName "'+$TaskName+'"')
$activatorTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(10)
Register-ScheduledTask -TaskName $activatorTask -Action $activatorAction -Trigger $activatorTrigger -Settings $helperSettings -Principal $helperPrincipal -Force | Out-Null
Write-Output 'agentos_ota_stage=ACTIVATING'
Write-Output ('agentos_ota_candidate='+$SourceCommit)
Write-Output 'agentos_ota_controller_acceptance=PENDING'
){throw 'Thin Client task is not using the expected PowerShell supervisor'}
$actionArgs=[string]$registeredAction.Arguments
if($actionArgs -notmatch '(?i)-File\s+"([^"]+)"'){throw 'Thin Client supervisor path could not be resolved from task action'}
$supervisorPath=[string]$Matches[1]
$installPrefix=[System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\\')+'\\'
$supervisorFull=[System.IO.Path]::GetFullPath($supervisorPath)
if(-not $supervisorFull.StartsWith($installPrefix,[System.StringComparison]::OrdinalIgnoreCase)){throw 'Thin Client supervisor path is outside InstallRoot'}
$pythonExe=(& python -c "import sys; print(sys.executable)"|Select-Object -Last 1).Trim()
if(-not $pythonExe -or -not(Test-Path -LiteralPath $pythonExe)){throw 'Thin Client Python executable could not be resolved'}
$escapedCurrent=$currentFile.Replace("'","''")
$escapedState=$state.Replace("'","''")
$escapedPython=$pythonExe.Replace("'","''")
$escapedLog=(Join-Path $InstallRoot 'thin-client.log').Replace("'","''")
$supervisorBody=@(
  '$ErrorActionPreference=''Continue'''
  ('$currentFile='''+$escapedCurrent+'''')
  ('$env:AGENTOS_CLIENT_HOME='''+$escapedState+'''')
  'while($true){'
  '  $rc=1'
  '  try{'
  '    $current=Get-Content -Raw -LiteralPath $currentFile|ConvertFrom-Json'
  '    $runtime=[string]$current.path'
  '    if(-not $runtime -or -not(Test-Path -LiteralPath $runtime)){throw ''current runtime path missing''}'
  '    $env:PYTHONPATH=$runtime'
  '    $env:AGENTOS_RUNTIME_PROVENANCE=Join-Path $runtime ''runtime-provenance.json'''
  ('    & '''+$escapedPython+''' -m agentos_node.client_cli run *>> '''+$escapedLog+'''')
  '    $rc=$LASTEXITCODE'
  '  }catch{'
  ('    Add-Content -LiteralPath '''+$escapedLog+''' -Value (''[supervisor] ''+$_.Exception.GetType().Name+'' at ''+[DateTimeOffset]::UtcNow.ToString(''o''))')
  '  }'
  ('  Add-Content -LiteralPath '''+$escapedLog+''' -Value (''[supervisor] client exited rc=''+$rc+'' at ''+[DateTimeOffset]::UtcNow.ToString(''o''))')
  '  Start-Sleep -Seconds 5'
  '}'
)-join [Environment]::NewLine
$supervisorBody|Set-Content -Encoding UTF8 -LiteralPath $supervisorFull
$supervisorCheck=Get-Content -Raw -LiteralPath $supervisorFull
if($supervisorCheck -notmatch 'current\.json'){throw 'Thin Client supervisor migration validation failed'}
$record|Add-Member -NotePropertyName supervisor_carrier -NotePropertyValue $supervisorFull -Force
$guardUrl="https://raw.githubusercontent.com/$Repo/$ToolCommit/scripts/windows/transactional_ota_guard.ps1"
$finalizeUrl="https://raw.githubusercontent.com/$Repo/$ToolCommit/scripts/windows/transactional_ota_finalize.ps1"
$guardPath=Join-Path $InstallRoot ("transactional_ota_guard-"+$SourceCommit+".ps1")
$finalizePath=Join-Path $InstallRoot ("transactional_ota_finalize-"+$SourceCommit+".ps1")
Invoke-WebRequest -UseBasicParsing -Uri $guardUrl -OutFile $guardPath
Invoke-WebRequest -UseBasicParsing -Uri $finalizeUrl -OutFile $finalizePath
$record|Add-Member -NotePropertyName guard_helper -NotePropertyValue $guardPath -Force
$record|Add-Member -NotePropertyName finalize_helper -NotePropertyValue $finalizePath -Force
$guardTask='AgentOS Thin Client OTA Guard'
$guardAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "'+$guardPath+'"')
$guardTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(4)
Register-ScheduledTask -TaskName $guardTask -Action $guardAction -Trigger $guardTrigger -Force | Out-Null
Write-JsonAtomic $record $currentFile
Move-Item -Force $next $launcher
$activatorTask='AgentOS Thin Client OTA Activator'
$activatorScript=Join-Path $InstallRoot ("transactional_ota_activate-"+$SourceCommit+".ps1")
@(
  "param([string]`$TaskName='AgentOS Thin Client')",
  "`$ErrorActionPreference='Stop'",
  "Stop-ScheduledTask -TaskName `$TaskName -ErrorAction SilentlyContinue",
  "Start-Sleep -Seconds 2",
  "`$clients=@(Get-CimInstance Win32_Process | Where-Object { `$_.Name -match '^pythonw?\.exe$' -and `$_.CommandLine -match '(?i)-m\s+agentos_node\.client_cli\s+run(?:\s|$)' })",
  "foreach(`$client in `$clients){ Stop-Process -Id `$client.ProcessId -Force -ErrorAction SilentlyContinue }",
  "for(`$i=0;`$i -lt 20;`$i++){ `$remaining=@(Get-CimInstance Win32_Process | Where-Object { `$_.Name -match '^pythonw?\.exe$' -and `$_.CommandLine -match '(?i)-m\s+agentos_node\.client_cli\s+run(?:\s|$)' }); if(`$remaining.Count -eq 0){break}; Start-Sleep -Milliseconds 500 }",
  "Start-ScheduledTask -TaskName `$TaskName",
  "Start-Sleep -Seconds 3",
  "`$task=Get-ScheduledTask -TaskName `$TaskName -ErrorAction Stop",
  "if([string]`$task.State -ne 'Running'){ throw 'Thin Client scheduled task did not enter Running state' }",
  "Write-Output 'agentos_ota_activator=PASS'"
)|Set-Content -Encoding ASCII $activatorScript
$record|Add-Member -NotePropertyName activator_helper -NotePropertyValue $activatorScript -Force
$activatorAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -File "'+$activatorScript+'" -TaskName "'+$TaskName+'"')
$activatorTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(10)
Register-ScheduledTask -TaskName $activatorTask -Action $activatorAction -Trigger $activatorTrigger -Force | Out-Null
Write-Output 'agentos_ota_stage=ACTIVATING'
Write-Output ('agentos_ota_candidate='+$SourceCommit)
Write-Output 'agentos_ota_controller_acceptance=PENDING'

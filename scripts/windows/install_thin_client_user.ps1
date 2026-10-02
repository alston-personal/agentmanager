param(
  [string]$TaskName = "AgentOS Thin Client",
  [string]$ClientHome = "$env:USERPROFILE\.agentos"
)

$ErrorActionPreference = "Stop"

$agentosClient = (Get-Command agentos-client -ErrorAction Stop).Source
$clientConfig = Join-Path $ClientHome "client.json"
$policyConfig = Join-Path $ClientHome "policy.json"

if (-not (Test-Path $clientConfig)) {
  throw "Missing $clientConfig. Enroll this node before installing the background task."
}
if (-not (Test-Path $policyConfig)) {
  throw "Missing $policyConfig. Run agentos-client policy-init first."
}

$action = New-ScheduledTaskAction `
  -Execute $agentosClient `
  -Argument "--config `"$clientConfig`" --policy `"$policyConfig`" run"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 10 `
  -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal `
  -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Installed and started per-user AgentOS Thin Client background task: $TaskName"
Write-Host "This intentionally runs in the logged-in user session so desktop tools such as Antigravity remain visible to the Node."

# Install an independent watchdog so an intentional stop or failed Thin Client
# cannot leave the node permanently offline.
$watchdogSource = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "thin_client_watchdog.ps1"
$watchdogTargetDir = Join-Path $env:LOCALAPPDATA "AgentOS\scripts"
$watchdogTarget = Join-Path $watchdogTargetDir "thin_client_watchdog.ps1"
if (-not (Test-Path $watchdogSource)) { throw "Missing watchdog script: $watchdogSource" }
New-Item -ItemType Directory -Force -Path $watchdogTargetDir | Out-Null
Copy-Item -Force -LiteralPath $watchdogSource -Destination $watchdogTarget

$watchdogTaskName = "$TaskName Watchdog"
$watchdogArgs = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $watchdogTarget + '" -TaskName "' + $TaskName + '" -ClientHome "' + $ClientHome + '"'
$watchdogAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $watchdogArgs
$watchdogLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogPeriodicTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$watchdogSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$watchdogPrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $watchdogTaskName -Action $watchdogAction -Trigger @($watchdogLogonTrigger,$watchdogPeriodicTrigger) -Settings $watchdogSettings -Principal $watchdogPrincipal -Force | Out-Null
Start-ScheduledTask -TaskName $watchdogTaskName
Write-Host "Installed and started AgentOS Thin Client watchdog task: $watchdogTaskName"


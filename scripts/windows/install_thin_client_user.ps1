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

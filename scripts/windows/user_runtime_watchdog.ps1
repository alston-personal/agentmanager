param(
  [Parameter(Mandatory=$true)]
  [string]$Runner
)

$ErrorActionPreference='SilentlyContinue'

while($true){
  $client=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match 'agentos_node\.client_cli' -and
      $_.CommandLine -match '\brun\b'
    } |
    Select-Object -First 1

  if(-not $client){
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
      '-NoProfile',
      '-NonInteractive',
      '-WindowStyle','Hidden',
      '-ExecutionPolicy','Bypass',
      '-File',$Runner
    )
  }

  Start-Sleep -Seconds 60
}

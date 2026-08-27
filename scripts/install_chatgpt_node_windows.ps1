param(
    [string]$OneUrl = "https://studio.milkcat.org/dashboard/api/agentos",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"

if (-not $env:AGENTOS_CONTROL_PLANE_TOKEN) {
    throw "AGENTOS_CONTROL_PLANE_TOKEN is required before installing the ChatGPT node."
}

python -m pip install --upgrade -e $RepoRoot

$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$companionToken = [Convert]::ToHexString($bytes).ToLowerInvariant()

[Environment]::SetEnvironmentVariable("AGENTOS_CONTROL_PLANE_URL", $OneUrl, "User")
[Environment]::SetEnvironmentVariable("AGENTOS_CONTROL_PLANE_TOKEN", $env:AGENTOS_CONTROL_PLANE_TOKEN, "User")
[Environment]::SetEnvironmentVariable("AGENTOS_CHATGPT_COMPANION_TOKEN", $companionToken, "User")
[Environment]::SetEnvironmentVariable("AGENTOS_CHATGPT_COMPANION_PORT", "$Port", "User")

$startup = [Environment]::GetFolderPath("Startup")
$launcher = Join-Path $startup "LeopardCat-AgentOS-ChatGPT-Node.cmd"
$scriptPath = Join-Path $RepoRoot "scripts\chatgpt_local_companion.py"
@"
@echo off
set AGENTOS_CONTROL_PLANE_URL=$OneUrl
set AGENTOS_CONTROL_PLANE_TOKEN=$env:AGENTOS_CONTROL_PLANE_TOKEN
set AGENTOS_CHATGPT_COMPANION_TOKEN=$companionToken
set AGENTOS_CHATGPT_COMPANION_PORT=$Port
start "AgentOS ChatGPT Node" /min python "$scriptPath"
"@ | Set-Content -Path $launcher -Encoding ASCII

Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $launcher -WindowStyle Hidden

$extensionPath = Join-Path $RepoRoot "browser\chatgpt-agentos-node"
Write-Host ""
Write-Host "ChatGPT AgentOS node companion installed." -ForegroundColor Green
Write-Host "ONE: $OneUrl"
Write-Host "Companion: http://127.0.0.1:$Port"
Write-Host "Extension folder: $extensionPath"
Write-Host "Companion token (paste into extension popup):"
Write-Host $companionToken -ForegroundColor Yellow
Write-Host ""
Write-Host "Chrome/Edge: Extensions -> Developer mode -> Load unpacked -> select the extension folder."
Write-Host "Then open ChatGPT, click the AgentOS extension, save the token and bind the current chat to an AgentOS project_id."

@echo off
setlocal EnableExtensions
title AgentOS Node Join

set "AGENTOS_REPO=alston-personal/agentmanager"
set "AGENTOS_REF=core/integration"
set "AGENTOS_NODE_ID=%~1"
if "%AGENTOS_NODE_ID%"=="" set "AGENTOS_NODE_ID=%COMPUTERNAME%"

echo.
echo ============================================================
echo  AgentOS Node Join
echo ============================================================
echo  Node ID : %AGENTOS_NODE_ID%
echo  Source  : %AGENTOS_REPO% / %AGENTOS_REF%
echo.
echo  This computer will be enrolled as an AgentOS Node.
echo  Keep this window open until PASS is shown.
echo ============================================================
echo.

set "AGENTOS_BOOTSTRAP=%TEMP%\agentos-bootstrap-clean-windows.ps1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$repo='%AGENTOS_REPO%'; $ref='%AGENTOS_REF%';" ^
  "$h=@{'Accept'='application/vnd.github+json';'User-Agent'='AgentOS-Join/0.1';'Cache-Control'='no-cache'};" ^
  "$e=[uri]::EscapeDataString($ref);" ^
  "$c=Invoke-RestMethod -UseBasicParsing -Headers $h -Uri ('https://api.github.com/repos/'+$repo+'/commits/'+$e);" ^
  "$sha=[string]$c.sha;" ^
  "if($sha -notmatch '^[0-9a-f]{40}$'){throw 'Failed to resolve AgentOS source commit'};" ^
  "$u='https://raw.githubusercontent.com/'+$repo+'/'+$sha+'/scripts/bootstrap_clean_windows_node.ps1';" ^
  "Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri $u -OutFile '%AGENTOS_BOOTSTRAP%';" ^
  "Write-Host ('agentos_join_bootstrap_commit='+$sha)"

if errorlevel 1 goto :fail

if /I "%AGENTOS_JOIN_DRY_RUN%"=="1" (
  echo agentos_join_dry_run=PASS
  echo agentos_join_bootstrap=%AGENTOS_BOOTSTRAP%
  exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%AGENTOS_BOOTSTRAP%" -NodeId "%AGENTOS_NODE_ID%" -SourceRef "%AGENTOS_REF%"
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo  AgentOS Node Join: PASS
echo  Node ID: %AGENTOS_NODE_ID%
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo ============================================================
echo  AgentOS Node Join: FAILED
echo  Exit code: %ERRORLEVEL%
echo ============================================================
echo  Keep this window open and send the error output to AgentOS.
echo.
pause
exit /b 1

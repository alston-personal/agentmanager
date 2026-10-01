@echo off
setlocal EnableExtensions
title AgentOS One-Click Installer

set "BOOTSTRAP=%TEMP%\agentos-one-click-%RANDOM%-%RANDOM%.ps1"
set "URL=https://raw.githubusercontent.com/alston-personal/agentmanager/main/install-agentos.ps1"

echo AgentOS One-Click Installer
echo Downloading canonical installer...
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%URL%' -OutFile '%BOOTSTRAP%'"
if errorlevel 1 goto :fail

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BOOTSTRAP%"
set "RC=%ERRORLEVEL%"
del /q "%BOOTSTRAP%" >nul 2>&1

if not "%RC%"=="0" goto :failcode
echo.
echo AgentOS installation completed successfully.
pause
exit /b 0

:fail
set "RC=%ERRORLEVEL%"
:failcode
echo.
echo AgentOS installation did not complete. Exit code: %RC%
echo Keep this window open and send the error text to the AgentOS assistant.
pause
exit /b %RC%

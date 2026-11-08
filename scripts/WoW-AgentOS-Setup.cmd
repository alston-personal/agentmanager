@echo off
setlocal
title AgentOS WoW Setup - Preflight
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0wow_agentos_installer_preflight.ps1"
set "code=%ERRORLEVEL%"
echo.
echo This tool only checks compatibility. The full installer is not released.
pause
exit /b %code%

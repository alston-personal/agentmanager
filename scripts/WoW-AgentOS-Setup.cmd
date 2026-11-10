@echo off
setlocal
title AgentOS WoW V1 - Offline Addon Installer (Preview)
echo AgentOS WoW preview installer
echo This installs the Addon UI and read-only reply slot only.
echo The ONE Bridge is NOT yet connected.
echo.
set "WOWROOT="
rem Scope execution-policy choice to this PowerShell process only.
rem Suppress selector errors from stdout, never interpret errors as game paths.
for /f "usebackq delims=" %%G in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0wow_agentos_select_game.ps1" 2^>nul`) do (
  if not defined WOWROOT set "WOWROOT=%%G"
)
if not defined WOWROOT goto no_game
if not exist "%WOWROOT%\_forever_\Wow.exe" goto no_game
if not exist "%WOWROOT%\_forever_\Interface\AddOns\" goto no_game
echo Selected WoW installation: "%WOWROOT%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0wow_agentos_install.ps1" -Mode Install -WowRoot "%WOWROOT%"
set "code=%ERRORLEVEL%"
echo.
if not "%code%"=="0" echo Installation failed. Read the PowerShell error above.
pause
exit /b %code%
:no_game
echo WoW Forever was not found or the selection script was blocked.
echo Your machine may enforce Group Policy. Nothing was changed.
pause
exit /b 2

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
if not "%code%"=="0" goto install_failed
if exist "%LOCALAPPDATA%\AgentOS\state\client.json" goto finish
echo Offline Addon UI installed. No default AgentOS Node enrollment was found.
echo The existing AgentOS Join process can connect this PC to the ONE Realm.
echo Joining may require downloading components and approval from the Realm administrator.
echo If this PC already has a Node installed elsewhere, do NOT join a second Node.
call "%~dp0..\Join-AgentOS-Node.cmd"
if errorlevel 1 echo Node enrollment did not complete. The offline Addon is still installed.
goto finish
:install_failed
echo Installation failed. Read the PowerShell error above.
pause
exit /b %code%
:finish
echo Installation finished. Chat remains disabled until an authorized ONE Bridge is verified.
pause
exit /b 0
:no_game
echo WoW Forever was not found or the selection script was blocked.
echo Your machine may enforce Group Policy. Nothing was changed.
pause
exit /b 2

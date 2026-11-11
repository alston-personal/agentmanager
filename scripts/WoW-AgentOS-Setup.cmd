@echo off
setlocal EnableExtensions
title AgentOS WoW Installer V1 Preview
echo AgentOS WoW preview installer
echo This adds the offline WoW UI and reuses the existing AgentOS Node Join.
echo ONE chat requires a separately verified local Bridge.
echo.
set "WOWROOT="
for /f "usebackq delims=" %%G in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0wow_agentos_select_game.ps1" 2^>nul`) do (
  if not defined WOWROOT set "WOWROOT=%%G"
)
if not defined WOWROOT goto no_game
if not exist "%WOWROOT%\_forever_\Wow.exe" goto no_game
if not exist "%WOWROOT%\_forever_\Interface\AddOns\" goto no_game
echo Selected WoW installation: "%WOWROOT%"
set "ADDONS=%WOWROOT%\_forever_\Interface\AddOns"
if exist "%ADDONS%\AgentOSWoW\" if exist "%ADDONS%\AgentOSWoW_R001\" goto existing_addons
if exist "%ADDONS%\AgentOSWoW\" goto partial_addons
if exist "%ADDONS%\AgentOSWoW_R001\" goto partial_addons
goto node_check
:existing_addons
echo The existing AgentOS WoW Addons were detected.
echo They will be preserved, not overwritten or reinstalled.
:node_check
if exist "%LOCALAPPDATA%\AgentOS\state\client.json" goto install_addon
echo.
echo No AgentOS Node enrollment found in the default location.
echo The setup will offer the existing AgentOS Node Join in this same flow.
echo If an AgentOS Node exists at another location, do NOT create a second Node.
call "%~dp0..\Join-AgentOS-Node.cmd"
if exist "%LOCALAPPDATA%\AgentOS\state\client.json" goto install_addon
echo.
echo Node Join was skipped, failed, or still awaits Realm approval.
echo You may install the offline UI now, but live ONE chat will remain disabled.
set "OFFLINEANSWER="
set /p "OFFLINEANSWER=Type OFFLINE to continue offline, or Enter to stop: "
if /I not "%OFFLINEANSWER%"=="OFFLINE" goto join_incomplete
:install_addon
if exist "%ADDONS%\AgentOSWoW\" if exist "%ADDONS%\AgentOSWoW_R001\" goto finish
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0wow_agentos_install.ps1" -Mode Install -WowRoot "%WOWROOT%"
set "code=%ERRORLEVEL%"
if not "%code%"=="0" goto install_failed
goto finish
:partial_addons
echo Only one AgentOS WoW Addon directory exists. Cannot safely overwrite.
echo Preserve game files and inspect the existing installation.
pause
exit /b 3
:join_incomplete
echo Node Join incomplete; existing Addons have not been modified.
pause
exit /b 4
:install_failed
echo Installation failed. Read the PowerShell error above.
pause
exit /b %code%
:finish
echo WoW Addons present. Node enrollment and ONE Bridge are separate checks.
echo Enter the game and type /agentos; chat stays disabled until Bridge verification.
pause
exit /b 0
:no_game
echo WoW Forever was not found or the selection script was blocked.
echo Your machine may enforce Group Policy. Nothing was changed.
pause
exit /b 2

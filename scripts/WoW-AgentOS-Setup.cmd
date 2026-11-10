@echo off
setlocal
title AgentOS WoW V1 - Offline Addon Installer (Preview)
echo AgentOS WoW preview installer
echo This installs the Addon UI and read-only reply slot only.
echo The ONE Bridge is NOT yet connected.
echo.
set "WOWROOT="
for /f "usebackq delims=" %%G in (`powershell.exe -NoProfile -File "%~dp0wow_agentos_select_game.ps1"`) do (
  if not defined WOWROOT set "WOWROOT=%%G"
)
if not defined WOWROOT (
  echo Compatible WoW Forever folder not selected. Nothing was changed.
  pause
  exit /b 2
)
echo Selected WoW installation: "%WOWROOT%"
powershell.exe -NoProfile -File "%~dp0wow_agentos_install.ps1" -Mode Install -WowRoot "%WOWROOT%"
set "code=%ERRORLEVEL%"
echo.
if not "%code%"=="0" echo Installation was not completed. Review the message above.
pause
exit /b %code%

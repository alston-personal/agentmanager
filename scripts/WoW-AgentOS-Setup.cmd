@echo off
setlocal
title AgentOS WoW V1 - Offline Addon Installer (Preview)
echo AgentOS WoW preview installer
echo This installs the Addon UI and read-only reply slot only.
echo The ONE Bridge is NOT yet connected.
echo.
set /p "WOWROOT=Enter your World of Warcraft root folder (containing _forever_): "
if not defined WOWROOT (
  echo No game folder supplied. Nothing was changed.
  exit /b 2
)
powershell.exe -NoProfile -File "%~dp0wow_agentos_install.ps1" -Mode Install -WowRoot "%WOWROOT%"
set "code=%ERRORLEVEL%"
echo.
if not "%code%"=="0" echo Installation was not completed. Review the message above.
pause
exit /b %code%

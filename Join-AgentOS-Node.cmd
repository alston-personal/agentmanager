@echo off
setlocal
title AgentOS Existing Windows Node Join
if not exist "%~dp0scripts\AgentOS-Join.cmd" (
  echo Missing verified AgentOS Node Join payload.
  pause
  exit /b 2
)
echo This will start the existing AgentOS Node enrollment.
echo It may download approved AgentOS components and require Realm approval.
echo No WoW Addon files are changed by this action.
echo.
set /p "ANSWER=Type JOIN to proceed, or press Enter to cancel: "
if /I not "%ANSWER%"=="JOIN" (
  echo Node enrollment skipped.
  pause
  exit /b 2
)
call "%~dp0scripts\AgentOS-Join.cmd"
exit /b %ERRORLEVEL%

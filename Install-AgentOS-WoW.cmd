@echo off
setlocal
title AgentOS WoW Installer V1 Preview
if not exist "%~dp0scripts\WoW-AgentOS-Setup.cmd" (
  echo Missing installer payload. Nothing has been changed.
  pause
  exit /b 2
)
call "%~dp0scripts\WoW-AgentOS-Setup.cmd"
exit /b %ERRORLEVEL%

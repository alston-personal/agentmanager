@echo off
setlocal
title AgentOS Node One-Click Join
color 0b

echo ============================================================
echo   AgentOS Universal Node One-Click Join (Windows)
echo ============================================================
echo.
echo [1/3] Connecting to Central ONE Realm (studio.milkcat.org)...
echo [2/3] Launching background automated bootstrap and handshake...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://studio.milkcat.org/join | iex"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo   [SUCCESS] Node successfully enrolled and connected!
    echo   Thin Client daemon is now running in the background.
    echo ============================================================
) else (
    echo.
    echo [ERROR] Join process encountered an error. Exit code: %ERRORLEVEL%
)

echo.
echo You may close this window.
timeout /t 10

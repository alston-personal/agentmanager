@echo off
title Mount QMD Network Share
echo ===================================================
echo 🗺️ Connecting to QMD Network Share (10.135.101.152)
echo ===================================================
echo.

:: Clear existing connection to avoid resource-in-use conflicts
echo 🧹 Cleaning up any existing connections...
net use \\10.135.101.152\QMD /delete /y >nul 2>&1

:: Mount network share persistently
echo 📥 Mounting network share...
net use \\10.135.101.152\QMD qmd /user:qmd /persistent:yes

if %errorlevel% equ 0 (
    echo.
    echo ✅ [SUCCESS] Mounted \\10.135.101.152\QMD successfully!
) else (
    echo.
    echo ❌ [ERROR] Failed to mount network share. (Error Code: %errorlevel%)
)
echo.
pause

@echo off
title SMB Network Share Diagnostic Tool
setlocal enabledelayedexpansion

set TARGET_IP=10.135.101.152
set TARGET_SHARE=\\10.135.101.152\QMD

echo =============================================================
echo 🩺 SMB/Samba Network Share Diagnostic Tool
echo Target Share: %TARGET_SHARE%
echo =============================================================
echo.

set FAILURES=0

:: 0. Pre-Check: Is the share already mounted and accessible?
echo 🔍 [Pre-Check] Testing if share is already accessible...
dir %TARGET_SHARE% >nul 2>&1
if %errorlevel% equ 0 (
    set SHARE_ACCESSIBLE=1
    echo    🎉 [SUCCESS] The network share is already connected and accessible!
) else (
    set SHARE_ACCESSIBLE=0
    echo    ℹ️ Target share is not currently accessible [proceeding with diagnostics].
)
echo.

:: 1. Ping test (Network Layer)
echo 🔍 [Test 1] Testing ICMP ping to %TARGET_IP%...
ping -n 2 -w 1000 %TARGET_IP% >nul
if %errorlevel% equ 0 (
    echo    ✅ Network reachable [Ping Success].
) else (
    echo    ❌ Network unreachable [Ping Failed].
    echo       Check your network cable, Wi-Fi connection, or firewall.
    set /a FAILURES+=1
)
echo.

:: 2. TCP Port 445 Test (Transport Layer - SMB port)
echo 🔍 [Test 2] Testing TCP Port 445 [SMB] connection via PowerShell...
powershell -Command "$t = New-Object System.Net.Sockets.TcpClient; $t.Connect('%TARGET_IP%', 445); if ($t.Connected) { write-output 'CONNECTED' } else { write-output 'FAILED' }" 2>nul | findstr /i "CONNECTED" >nul
if %errorlevel% equ 0 (
    echo    ✅ TCP Port 445 is OPEN [Server is listening for SMB requests].
) else (
    echo    ❌ TCP Port 445 is CLOSED or Blocked!
    echo       The target server might be offline, Samba service might be stopped, 
    echo       or a local/network firewall is blocking SMB traffic.
    set /a FAILURES+=1
)
echo.

:: 3. LanmanWorkstation Client Service check
echo 🔍 [Test 3] Checking Windows Workstation [LanmanWorkstation] Service...
sc query LanmanWorkstation | findstr /i "RUNNING" >nul
if %errorlevel% equ 0 (
    echo    ✅ Workstation Service is RUNNING.
) else (
    echo    ❌ Workstation Service is NOT running!
    echo       This Windows service is required to connect to network shares.
    echo       Run 'net start LanmanWorkstation' in Administrator Command Prompt.
    set /a FAILURES+=1
)
echo.

:: 4. Active Connections / Session Conflict Check
echo 🔍 [Test 4] Scanning for active SMB sessions...
net use | findstr /i "%TARGET_IP%" >temp_netuse.txt 2>nul
set CONFLICT_FOUND=0
for /f "delims=" %%a in (temp_netuse.txt) do (
    set CONFLICT_FOUND=1
    echo    ⚠️ Existing session found: %%a
)
del temp_netuse.txt >nul 2>&1

if !CONFLICT_FOUND! equ 0 (
    echo    ✅ No existing sessions found to %TARGET_IP%.
) else (
    if %SHARE_ACCESSIBLE% equ 1 (
        echo    ✅ Active session is currently connected and working.
    ) else (
        echo    ⚠️ Session detected. If you face access denied errors, this might be a conflict.
        echo       To clear: net use \\%TARGET_IP% /delete /y
    )
)
echo.

:: 5. Cached Credentials Check
echo 🔍 [Test 5] Checking Windows Credential Manager for cached keys...
cmdkey /list | findstr /i "%TARGET_IP%" >temp_cmdkey.txt 2>nul
set CACHE_FOUND=0
for /f "delims=" %%a in (temp_cmdkey.txt) do (
    set CACHE_FOUND=1
    echo    ⚠️ Cached credential found: %%a
)
del temp_cmdkey.txt >nul 2>&1

if !CACHE_FOUND! equ 0 (
    echo    ✅ No cached credentials found for %TARGET_IP%.
) else (
    if %SHARE_ACCESSIBLE% equ 1 (
        echo    ✅ Cached credentials exist [Currently working].
    ) else (
        echo    ⚠️ Cached credentials found. If you recently changed your password, Windows might use this old password automatically.
        echo       To clear: cmdkey /delete:Domain:target=%TARGET_IP%
    )
)
echo.

:: Diagnostic Summary
echo =============================================================
echo 📊 DIAGNOSTIC SUMMARY:
echo =============================================================
if %FAILURES% equ 0 (
    echo    ✨ [HEALTHY] Connection environment is healthy!
    if %SHARE_ACCESSIBLE% equ 1 (
        echo    The share is already successfully mounted and accessible.
    ) else (
        echo    Ready to connect. Please run your mount script to connect.
    )
) else (
    echo    ⚠️ Diagnostic found %FAILURES% critical connection issue(s) that need attention!
    echo.
    echo    Recommended Fix Actions:
    echo    1. Check your network ping or port status above.
    echo    2. If you have credential errors, try:
    echo       - cmdkey /delete:Domain:target=%TARGET_IP%
    echo       - net use \\%TARGET_IP% /delete /y
)
echo =============================================================
echo.
pause

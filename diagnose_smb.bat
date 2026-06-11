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

:: 1. Ping test (Network Layer)
echo 🔍 [Test 1] Testing ICMP ping to %TARGET_IP%...
ping -n 2 -w 1000 %TARGET_IP% >nul
if %errorlevel% equ 0 (
    echo    ✅ Network reachable (Ping Success).
) else (
    echo    ❌ Network unreachable (Ping Failed).
    echo       Check your network cable, Wi-Fi connection, or firewall.
    set /a FAILURES+=1
)
echo.

:: 2. TCP Port 445 Test (Transport Layer - SMB port)
echo 🔍 [Test 2] Testing TCP Port 445 (SMB) connection via PowerShell...
powershell -Command "$t = New-Object System.Net.Sockets.TcpClient; $t.Connect('%TARGET_IP%', 445); if ($t.Connected) { write-output 'CONNECTED' } else { write-output 'FAILED' }" 2>nul | findstr /i "CONNECTED" >nul
if %errorlevel% equ 0 (
    echo    ✅ TCP Port 445 is OPEN (Server is listening for SMB requests).
) else (
    echo    ❌ TCP Port 445 is CLOSED or Blocked!
    echo       The target server might be offline, Samba service might be stopped, 
    echo       or a local/network firewall is blocking SMB traffic.
    set /a FAILURES+=1
)
echo.

:: 3. LanmanWorkstation Client Service check
echo 🔍 [Test 3] Checking Windows Workstation (LanmanWorkstation) Service...
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
echo 🔍 [Test 4] Scanning for conflicting active SMB sessions...
net use | findstr /i "%TARGET_IP%" >temp_netuse.txt 2>nul
set CONFLICT_FOUND=0
for /f "delims=" %%a in (temp_netuse.txt) do (
    set CONFLICT_FOUND=1
    echo    ⚠️ Existing session found: %%a
)
del temp_netuse.txt >nul 2>&1

if !CONFLICT_FOUND! equ 0 (
    echo    ✅ No existing sessions found to %TARGET_IP% (No session conflicts).
) else (
    echo    ❌ Session conflict detected!
    echo       Windows only allows one user account per server at a time.
    echo       Run: net use \\%TARGET_IP% /delete /y
    set /a FAILURES+=1
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
    echo    ✅ No cached credentials found for %TARGET_IP% in Windows Credential Manager.
) else (
    echo    ❌ Cached credentials found!
    echo       Windows might be using an old/incorrect cached password automatically.
    echo       Run: cmdkey /delete:Domain:target=%TARGET_IP%
    set /a FAILURES+=1
)
echo.

:: Diagnostic Summary
echo =============================================================
echo 📊 DIAGNOSTIC SUMMARY:
echo =============================================================
if %FAILURES% equ 0 (
    echo    ✨ [HEALTHY] All checks passed!
    echo    If you still cannot connect, verify that your username ('qmd') 
    echo    and password are correct on the Samba server.
) else (
    echo    ⚠️ Diagnostic found %FAILURES% issue(s) that need attention!
    echo.
    echo    Recommended Fix Actions:
    echo    1. Run: cmdkey /delete:Domain:target=%TARGET_IP%
    echo    2. Run: net use \\%TARGET_IP% /delete /y
    echo    3. Retry your mount script.
)
echo =============================================================
echo.
pause

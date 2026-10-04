@echo off
rem ============================================================
rem  One-click mock test env builder for MaaAutoBoot.
rem  Put MaaAutoBoot.exe in THIS folder first, then run me.
rem ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_mock.ps1"
echo.
pause

@echo off
rem ============================================================
rem  Fake MAA assistant:
rem  MAA phase monitors ONLY the log marker (no stability wait),
rem  so: short alive time -> write marker (UTF-8) -> exit.
rem  Marker text is Chinese; written via write_marker.ps1 to
rem  guarantee UTF-8 bytes (cmd echo would write GBK and never match).
rem  Total lifetime ~13s.
rem ============================================================
ping -n 11 127.0.0.1 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0write_marker.ps1" -File "%~dp0debug\gui.log" -Text "任务已全部完成！"
ping -n 3 127.0.0.1 >nul

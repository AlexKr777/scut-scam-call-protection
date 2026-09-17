@echo off
setlocal
set "SCUT_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCUT_ROOT%scripts\first-run.ps1"
exit /b %ERRORLEVEL%

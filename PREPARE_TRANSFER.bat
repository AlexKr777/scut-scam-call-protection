@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare-transfer.ps1"
exit /b %ERRORLEVEL%

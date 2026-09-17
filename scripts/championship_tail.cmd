@echo off
echo Ctrl+C stops only this log viewer.
powershell.exe -NoProfile -Command "Get-Content -LiteralPath '%~dp0..\logs\scut_brain_championship_pc5070\worker.stdout.log' -Wait"

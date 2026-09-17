@echo off
echo Ctrl+C stops only this log viewer.
powershell.exe -NoProfile -Command "Get-Content -LiteralPath '%~dp0..\logs\audio_replay_v1\worker.stdout.log' -Wait"

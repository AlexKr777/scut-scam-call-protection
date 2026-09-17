@echo off
powershell.exe -NoProfile -Command "$root=(Resolve-Path '%~dp0..').Path; $dir=Join-Path $root 'runtime\audio_replay_v1'; New-Item -ItemType Directory -Force -Path $dir | Out-Null; Set-Content -LiteralPath (Join-Path $dir 'stop.request') -Value (Get-Date).ToUniversalTime().ToString('o') -Encoding UTF8; Write-Host 'Stop requested; worker will stop at the next safe case checkpoint.'"

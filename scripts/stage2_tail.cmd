@echo off
set "LOG=%~dp0..\logs\scut_semantic_brain_v2_pc5070\stage2.stdout.log"
if not exist "%LOG%" (
  echo Stage-2 stdout log not found: %LOG%
  exit /b 1
)
echo Following Stage-2 log. Press Ctrl+C to stop following.
powershell.exe -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 30 -Wait"

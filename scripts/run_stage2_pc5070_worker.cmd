@echo off
setlocal
set "ROOT=%~1"
set "PYTHON=%~2"
set "STATUS=%~3"
set "STDOUT=%~4"
set "STDERR=%~5"
cd /d "%ROOT%"
"%PYTHON%" scripts\run_e5_stage2.py --device cuda --batch-size 8 --output-dir output\scut_semantic_brain_v2_pc5070 --report-dir reports\scut_semantic_brain_v2_pc5070 >> "%STDOUT%" 2>> "%STDERR%"
set "EC=%ERRORLEVEL%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-Content -Raw '%STATUS%'|ConvertFrom-Json; $s.state=if (%EC% -eq 0) {'COMPLETED'} else {'FAILED'}; $s.exit_code=%EC%; $s.end_time_utc=[DateTime]::UtcNow.ToString('o'); $s|ConvertTo-Json|Set-Content -Encoding UTF8 '%STATUS%'"
exit /b %EC%

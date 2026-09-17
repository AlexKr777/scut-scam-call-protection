@echo off
setlocal
set "SCUT_ROOT=%~dp0"
set "PY=%SCUT_ROOT%.local\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo SCUT runtime is not ready. Run FIRST_RUN.bat first.
  exit /b 1
)
"%PY%" "%SCUT_ROOT%scripts\configure.py"

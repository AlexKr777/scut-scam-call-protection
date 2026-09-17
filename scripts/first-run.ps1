[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$local = Join-Path $root '.local'
$logs = Join-Path $root 'logs'
$cache = Join-Path $root 'bootstrap-cache'
New-Item -ItemType Directory -Force -Path $local,$logs,(Join-Path $root 'diagnostics') | Out-Null
$logPath = Join-Path $logs ('first-run-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
Start-Transcript -Path $logPath -Append | Out-Null
$statePath = Join-Path $local 'bootstrap-state.json'
# Windows PowerShell 5.1 does not support ConvertFrom-Json -AsHashtable.
# Keep the state mutable without requiring PowerShell 7.
$state = @{}
if (Test-Path $statePath) {
  try {
    $savedState = Get-Content $statePath -Raw | ConvertFrom-Json
    foreach ($property in $savedState.PSObject.Properties) {
      $state[$property.Name] = $property.Value
    }
  } catch { $state = @{} }
}
function Save-State { $state | ConvertTo-Json -Depth 5 | Set-Content -Path $statePath -Encoding UTF8 }
function Set-Stage {
  param([string]$Name, [string]$Status, [string]$Detail)
  $state[$Name] = @{ status=$Status; detail=$Detail; at=(Get-Date).ToString('o') }
  Save-State
  Write-Host ('[' + $Status + '] ' + $Name + ' - ' + $Detail)
}
function Invoke-ScutDownload {
  param([string]$Url, [string]$Destination, [string]$Hash='')
  if (-not $Url.StartsWith('https://')) { throw 'SCUT accepts HTTPS downloads only.' }
  if ((Test-Path $Destination) -and (Get-Item $Destination).Length -gt 1024) { return }
  $partial = "$Destination.partial"
  Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
  for ($attempt=1; $attempt -le 3; $attempt++) {
    try {
      Write-Host "Downloading (attempt $attempt/3): $Url"
      Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing -TimeoutSec 120
      if ((Get-Item $partial).Length -lt 1024) { throw 'Downloaded file is unexpectedly small.' }
      if ($Hash -and (Get-FileHash $partial -Algorithm SHA256).Hash -ne $Hash) { throw 'SHA-256 mismatch.' }
      Move-Item -LiteralPath $partial -Destination $Destination -Force
      return
    } catch {
      Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
      if ($attempt -eq 3) { throw }
      Start-Sleep -Seconds (2 * $attempt)
    }
  }
}
function Get-ScutPython {
  $python = Join-Path $local 'runtime\python.exe'
  if (Test-Path $python) { if ((& $python --version 2>&1) -match 'Python 3\.12\.') { return $python } }
  $installer = Join-Path $cache 'installers\python-3.12.10-amd64.exe'
  New-Item -ItemType Directory -Force -Path (Split-Path $installer) | Out-Null
  Invoke-ScutDownload 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' $installer
  $arguments = '/quiet InstallAllUsers=0 Include_pip=1 Include_test=0 PrependPath=0 TargetDir="' + (Join-Path $local 'runtime') + '"'
  $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
  # Some Python installers ignore a Unicode TargetDir on older Windows installer
  # engines. Use the just-installed user-local interpreter only as a bootstrap
  # source, then copy it into the project-local runtime and verify that copy.
  if (-not (Test-Path $python)) {
    $seed = ''
    try { $seed = (& py -3.12 -c 'import sys; print(sys.executable)' 2>$null).Trim() } catch {}
    if ($seed -and (Test-Path $seed)) {
      New-Item -ItemType Directory -Force -Path (Split-Path $python) | Out-Null
      Copy-Item -Path (Join-Path (Split-Path $seed) '*') -Destination (Split-Path $python) -Recurse -Force
    }
  }
  if ($process.ExitCode -ne 0 -or -not (Test-Path $python)) { throw "Python installer failed (exit $($process.ExitCode))." }
  return $python
}
try {
  $arch = (Get-CimInstance Win32_OperatingSystem).OSArchitecture
  $bluetooth = (Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue | Measure-Object).Count
  Set-Stage 'environment' 'PASS' "Windows $([Environment]::OSVersion.Version); $arch; Bluetooth adapters $bluetooth"
  $python = Get-ScutPython
  Set-Stage 'runtime' 'PASS' (& $python --version)
  $venv = Join-Path $local 'venv'; $venvPython = Join-Path $venv 'Scripts\python.exe'
  # A virtual environment embeds the absolute location of its base interpreter.
  # A copied project can therefore contain a venv from another PC or path.
  $venvHealthy = $false
  if (Test-Path $venvPython) {
    try {
      & $venvPython -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>$null
      $venvHealthy = $LASTEXITCODE -eq 0
    } catch { $venvHealthy = $false }
  }
  if (-not $venvHealthy) {
    if (Test-Path $venv) {
      Write-Host 'Replacing invalid project-local virtual environment.' -ForegroundColor Yellow
      Remove-Item -LiteralPath $venv -Recurse -Force
    }
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create project-local virtual environment.' }
  }
  & $venvPython -m pip install --upgrade pip | Out-Host
  $wheels = Join-Path $cache 'wheels'; $lock = Join-Path $root 'requirements.lock'; $wheelFiles = Get-ChildItem $wheels -Filter '*.whl' -ErrorAction SilentlyContinue
  if ($wheelFiles.Count -gt 0) { & $venvPython -m pip install --no-index --find-links $wheels -r $lock } else { & $venvPython -m pip install -r $lock }
  if ($LASTEXITCODE -ne 0) { throw 'Pinned runtime dependency install failed.' }
  Set-Stage 'dependencies' 'PASS' 'Pinned packages verified'
  $cachedModel = Join-Path $cache 'models\faster-whisper-small'; $localModel = Join-Path $local 'models\faster-whisper-small'
  if ((Test-Path (Join-Path $cachedModel 'model.bin')) -and -not (Test-Path (Join-Path $localModel 'model.bin'))) { New-Item -ItemType Directory -Force -Path (Split-Path $localModel) | Out-Null; Copy-Item $cachedModel $localModel -Recurse -Force }
  & $venvPython (Join-Path $root 'backend\whisper_engine.py') --prepare
  if ($LASTEXITCODE -ne 0) { Set-Stage 'whisper' 'FAIL' 'Model unavailable: rerun with internet or add verified cached model' } else { Set-Stage 'whisper' 'PASS' 'CPU baseline ready' }
  Set-Stage 'audio-helper' $(if (Test-Path (Join-Path $root 'windows-audio\audio_helper.py')) {'PASS'} else {'FAIL'}) 'Portable helper source checked'
  Set-Stage 'tailscale' $(if (Get-Command tailscale -ErrorAction SilentlyContinue) {'PASS'} else {'NEEDS LOGIN'}) 'Login is checked in Control Center'
  Set-Stage 'apk' $(if (Test-Path (Join-Path $root 'dist\SCUT.apk')) {'PASS'} else {'FAIL'}) 'APK presence checked'
  & $venvPython -m unittest discover -s (Join-Path $root 'tests') -v
  if ($LASTEXITCODE -ne 0) { throw 'Backend self-test failed.' }
  Set-Stage 'backend-self-test' 'PASS' 'Software tests passed'
} catch {
  Set-Stage 'fatal' 'FAIL' $_.Exception.Message
  Write-Host "FAILED STAGE: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Log: $logPath"
  Stop-Transcript | Out-Null
  exit 1
}
$bluetoothStatus = if ($bluetooth) {'PASS'} else {'NOT DETECTED'}
Write-Host '=================================================='
Write-Host 'SCUT FIRST RUN'
Write-Host '=================================================='
Write-Host "Windows                PASS"; Write-Host "Architecture           $arch"; Write-Host "Bluetooth              $bluetoothStatus"
Write-Host 'SCUT runtime           PASS'; Write-Host 'Python environment     PASS'
Write-Host ('Audio helper           ' + $state['audio-helper'].status); Write-Host ('Whisper                ' + $state['whisper'].status)
Write-Host ('APK                    ' + $state['apk'].status); Write-Host ('Tailscale              ' + $state['tailscale'].status)
Write-Host 'Software bootstrap     COMPLETE'
Write-Host 'Next: CONFIGURE.bat, pair Phone Link/Tailscale, install dist\SCUT.apk, START_SCUT.bat'
Write-Host '=================================================='
Stop-Transcript | Out-Null

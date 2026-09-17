[CmdletBinding()]
param([switch]$PackageMode)
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot;$fail=@();$username=[Environment]::UserName
$required=@('FIRST_RUN.bat','START_SCUT.bat','CONFIGURE.bat','PREPARE_TRANSFER.bat','BUILD_ANDROID.bat','PORTABILITY_CHECK.bat','README.md','requirements.lock','backend\server.py','windows-audio\scut-process-loopback.exe','android\app\src\main\AndroidManifest.xml')
foreach($item in $required){if(-not(Test-Path (Join-Path $root $item))){$fail+="Missing required portable file: $item"}}
if(Test-Path (Join-Path $root '.local')){if($PackageMode){$fail+='Machine-specific .local directory is present during package validation.'}else{Write-Host 'INFO: .local exists locally and will be excluded from transfer.'}}
if(Test-Path (Join-Path $root '.venv')){$fail+='Root .venv is forbidden; use .local\venv only.'}
$exclude='(^|[\\/])(\.local|\.venv|\.git|logs|output|\.playwright-cli)([\\/]|$)|(^|[\\/])__pycache__([\\/]|$)|(^|[\\/])bootstrap-cache[\\/](wheels|models|installers)([\\/]|$)|(^|[\\/])android[\\/](build|app[\\/]build|\.gradle)([\\/]|$)|\.obj$|SCUT-PORTABLE\.zip$'
$files=Get-ChildItem $root -File -Recurse|Where-Object{$_.FullName -notmatch $exclude}
$pathPattern=[regex]::Escape("C:\Users\$username\")
$secretPattern='(?i)(sk-[a-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*["'']?[a-z0-9_-]{16,}|authorization:\s*bearer\s+[a-z0-9._-]{16,})'
foreach($file in $files){try{$content=Get-Content $file.FullName -Raw -ErrorAction Stop;if($content -match $pathPattern){$fail+="Computer-A absolute path in $($file.FullName)"};if($content -match $secretPattern){$fail+="Possible secret in $($file.FullName)"}}catch{}}
if($fail.Count){Write-Host 'PORTABILITY FAIL' -ForegroundColor Red;$fail|ForEach-Object{Write-Host " - $_"};exit 1}
Write-Host 'PORTABILITY PASS — no required machine state, Computer-A path, or obvious credential found.' -ForegroundColor Green

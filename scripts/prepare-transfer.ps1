[CmdletBinding()]
param()
$ErrorActionPreference='Stop';$root=Split-Path -Parent $PSScriptRoot;$dist=Join-Path $root 'dist';$cache=Join-Path $root 'bootstrap-cache';New-Item -ItemType Directory -Force -Path $dist,(Join-Path $cache 'wheels')|Out-Null
$py=(Get-Command python -ErrorAction Stop).Source
& $py -m unittest discover -s (Join-Path $root 'tests') -v;if($LASTEXITCODE -ne 0){throw 'Tests failed; package not created.'}
& (Join-Path $root 'PORTABILITY_CHECK.bat');if($LASTEXITCODE -ne 0){throw 'Portability scan failed; package not created.'}
if(-not(Test-Path (Join-Path $dist 'SCUT.apk'))){throw 'dist\SCUT.apk is missing. Run BUILD_ANDROID.bat before packaging.'}
# Promote a verified local Hugging Face snapshot into the transferable model
# cache. This copies model data only; `.local` configuration/state remains out.
$modelCache=Join-Path $cache 'models\faster-whisper-small'
if(-not(Test-Path (Join-Path $modelCache 'model.bin'))){$sourceModel=Get-ChildItem (Join-Path $root '.local\models') -Recurse -Filter 'model.bin' -ErrorAction SilentlyContinue|Select-Object -First 1;if($sourceModel){New-Item -ItemType Directory -Force -Path $modelCache|Out-Null;Copy-Item -Path (Join-Path $sourceModel.Directory.FullName '*') -Destination $modelCache -Recurse -Force}}
# Cache exact Win x64/Python 3.12 wheels where the current network permits it. A failure does not corrupt prior cache.
try{& $py -m pip download --dest (Join-Path $cache 'wheels') --only-binary=:all: --platform win_amd64 --python-version 312 --implementation cp --abi cp312 -r (Join-Path $root 'requirements.lock');if($LASTEXITCODE -ne 0){Write-Warning 'Wheel cache is partial; FIRST_RUN will use official PyPI fallback.'}}catch{Write-Warning 'Wheel cache download unavailable; FIRST_RUN will use official PyPI fallback.'}
& (Join-Path $root 'PORTABILITY_CHECK.bat');if($LASTEXITCODE -ne 0){throw 'Portability scan failed after caching.'}
$zip=Join-Path $dist 'SCUT-PORTABLE.zip';Remove-Item $zip -Force -ErrorAction SilentlyContinue
$exclude='(^|[\\/])(\.local|\.venv|\.git|logs|output|\.playwright-cli)([\\/]|$)|(^|[\\/])__pycache__([\\/]|$)|(^|[\\/])android[\\/](build|app[\\/]build|\.gradle)([\\/]|$)|\.obj$|diagnostics[\\/].*\.(wav|json)$|SCUT-PORTABLE\.zip$|transfer-manifest\.json$'
$portable=Get-ChildItem $root -Recurse -File|Where-Object{$_.FullName -notmatch $exclude}
$revision='UNVERSIONED';try{$revision=(git -C $root rev-parse HEAD 2>$null)}catch{}
$manifest=[ordered]@{buildTimestamp=(Get-Date).ToUniversalTime().ToString('o');sourceRevision=$revision;windowsTargetArchitecture='x64';lockedDependencyFile='requirements.lock';apkSha256=(Get-FileHash (Join-Path $dist 'SCUT.apk') -Algorithm SHA256).Hash;cachedModel=$(if(Test-Path (Join-Path $modelCache 'model.bin')){'faster-whisper-small'}else{'MISSING'});cachedInstallers=@(Get-ChildItem (Join-Path $cache 'installers') -File|ForEach-Object Name);portableFiles=@($portable|ForEach-Object{[ordered]@{path=$_.FullName.Substring($root.Length+1);sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash;bytes=$_.Length}})}
$manifest|ConvertTo-Json -Depth 6|Set-Content (Join-Path $dist 'transfer-manifest.json') -Encoding UTF8
$stage=Join-Path $env:TEMP ('scut-package-stage-'+[guid]::NewGuid());New-Item -ItemType Directory -Force -Path $stage|Out-Null
foreach($file in $portable){$relative=$file.FullName.Substring($root.Length).TrimStart('\','/');$target=Join-Path $stage $relative;New-Item -ItemType Directory -Force -Path (Split-Path $target)|Out-Null;Copy-Item -LiteralPath $file.FullName -Destination $target -Force}
$manifestTarget=Join-Path $stage 'dist\transfer-manifest.json';New-Item -ItemType Directory -Force -Path (Split-Path $manifestTarget)|Out-Null;Copy-Item -LiteralPath (Join-Path $dist 'transfer-manifest.json') -Destination $manifestTarget -Force
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
$archiveCheck=Join-Path $env:TEMP ('scut-archive-check-'+[guid]::NewGuid());Expand-Archive -LiteralPath $zip -DestinationPath $archiveCheck -ErrorAction Stop
$forbidden=Get-ChildItem $archiveCheck -Recurse -Force|Where-Object{$_.FullName -match '(^|[\\/])(\.local|\.venv)([\\/]|$)|secrets\.json$'};Remove-Item -LiteralPath $stage -Recurse -Force;Remove-Item -LiteralPath $archiveCheck -Recurse -Force
if($forbidden.Count){throw 'Archive contains forbidden machine-specific state.'}
Write-Host "`n==================================================`nSCUT PORTABLE BUILD`n==================================================`nTests                   PASS`nPortability             PASS`nSecrets scan            PASS`nAPK                     PASS`nRuntime wheel cache     $(if((Get-ChildItem (Join-Path $cache 'wheels') -Filter '*.whl').Count){'READY'}else{'PARTIAL'})`nCreated: $zip`n==================================================" -ForegroundColor Green

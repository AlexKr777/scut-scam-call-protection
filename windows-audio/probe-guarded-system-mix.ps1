# Explicit real-call diagnostic. Keep all other render sources silent before invoking.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$diag = Join-Path $root 'diagnostics'
$raw = & (Join-Path $PSScriptRoot 'scut-guarded-system-mix.exe') --seconds 12 --wav (Join-Path $diag 'guarded_system_mix_call.wav')
$result = $raw | Select-Object -Last 1 | ConvertFrom-Json
$result | Add-Member -NotePropertyName timestamp -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o'))
$result | Add-Member -NotePropertyName classification -NotePropertyValue 'SYSTEM_MIX_GUARDED_NOT_PROCESS_ATTRIBUTED'
$result | Add-Member -NotePropertyName physicalCondition -NotePropertyValue 'Remote caller speaks continuously; local user, Chrome/media, and notifications silent.'
if ($result.callSentinelActive -and ($result.attempts | Where-Object signal)) { $result.state = 'GUARDED_SYSTEM_MIX_CANDIDATE' }
$result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $diag 'GUARDED_SYSTEM_MIX_CALL_DIAGNOSTIC.json') -Encoding UTF8

# Run only while the remote caller is continuously speaking and the local user is silent.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $PSScriptRoot 'scut-capture-endpoint.exe'
$diag = Join-Path $root 'diagnostics'
$beforePath = Join-Path $diag 'capture_snapshot_before.json'
$duringPath = Join-Path $diag 'capture_snapshot_during.json'
& $tool --snapshot $duringPath
$before = (Get-Content $beforePath -Raw | ConvertFrom-Json).endpoints
$during = (Get-Content $duringPath -Raw | ConvertFrom-Json).endpoints
$beforeById = @{}; $before | ForEach-Object { $beforeById[$_.endpointId] = $_ }
$candidates = @($during | Where-Object { $_.state -eq 'ACTIVE' -and $_.callRelatedName })
$attempts = @()
foreach ($candidate in $candidates) {
  $safe = ($candidate.endpointId -replace '[^a-zA-Z0-9]+','_').Trim('_')
  $wav = Join-Path $diag ("capture_call_$safe.wav")
  $raw = & $tool --endpoint $candidate.endpointId --seconds 8 --wav $wav
  $metric = $raw | Select-Object -Last 1 | ConvertFrom-Json
  $attempts += [ordered]@{ endpointName=$candidate.endpointName; endpointId=$candidate.endpointId; state=$candidate.state; beforeState=if($beforeById.ContainsKey($candidate.endpointId)){$beforeById[$candidate.endpointId].state}else{'NEW'}; wav=$wav; sampleRate=$metric.sampleRate; channels=$metric.channels; samples=$metric.samples; duration=$metric.duration; rms=$metric.rms; peak=$metric.peak; signal=$metric.signal; error=$metric.error; classification='UNVERIFIED_REMOTE_DIRECTION' }
}
$report = [ordered]@{ timestamp=(Get-Date).ToUniversalTime().ToString('o'); protocol='normal WASAPI eCapture; no loopback'; physicalCondition='Remote caller speaks continuously; local SCUT user silent'; beforeCall=$before; duringCall=$during; captureAttempts=$attempts; finalState=if($attempts.Count){'PCM_CAPTURED_REQUIRES_AUDIBLE_DIRECTIONAL_REVIEW'}else{'NO_ACTIVE_CALL_RELATED_CAPTURE_ENDPOINT'}; finalReason='Endpoint name and PCM alone never establish remote caller direction.' }
$report | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $diag 'PHONE_LINK_CAPTURE_PATH_DIAGNOSTIC.json') -Encoding UTF8

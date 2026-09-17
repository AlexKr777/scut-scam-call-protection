# Explicit headphone-routing validation; SYSTEM_MIX_GUARDED, never process-attributed.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$diag = Join-Path $root 'diagnostics'
$reportPath = Join-Path $diag 'HEADPHONES_PHONE_LINK_CAPTURE_DIAGNOSTIC.json'
$previous = if (Test-Path $reportPath) { Get-Content $reportPath -Raw | ConvertFrom-Json } else { $null }
$raw = & (Join-Path $PSScriptRoot 'scut-guarded-system-mix.exe') --seconds 12 --wav (Join-Path $diag 'headphones_phone_link_capture.wav')
$result = $raw | Select-Object -Last 1 | ConvertFrom-Json
$selected = @($result.attempts | Where-Object role -eq 'communications' | Select-Object -First 1)[0]
$changed = [bool]($previous -and $previous.communicationsEndpointId -ne $selected.endpointId)
$report = [ordered]@{ timestamp=(Get-Date).ToUniversalTime().ToString('o'); source='SYSTEM_MIX_GUARDED'; attribution='NOT_PROCESS_ATTRIBUTED'; state=if($result.callSentinelActive -and $selected.signal){'GUARDED_SYSTEM_MIX_CANDIDATE'}else{$result.state}; callSentinelActive=$result.callSentinelActive; communicationsEndpointName=$selected.endpointName; communicationsEndpointId=$selected.endpointId; endpointRole='eCommunications'; endpointChanged=$changed; previousCommunicationsEndpointId=if($previous){$previous.communicationsEndpointId}else{$null}; loopbackTap=$result.loopbackTap; muteExperiment=@{result='PRE_VOLUME_PRE_MUTE_CONFIRMED'; mutedToneRms=9349.043; mutedTonePeak=32278}; otherActiveRenderSessions=$result.otherActiveRenderSessions; metrics=$selected; physicalPass='REQUIRES_USER_CONFIRMATION: laptop speakers silent, caller audible in headphones, WAV contains same caller.' }
$report | ConvertTo-Json -Depth 8 | Set-Content $reportPath -Encoding UTF8

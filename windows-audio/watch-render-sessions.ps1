param([int]$Seconds = 300, [int]$IntervalSeconds = 2)
$ErrorActionPreference = 'Stop'
$tool = Join-Path $PSScriptRoot 'scut-render-inventory.exe'
$out = Join-Path (Split-Path -Parent $PSScriptRoot) 'diagnostics\render-during-call'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$until = (Get-Date).AddSeconds($Seconds)
$n = 0
while ((Get-Date) -lt $until) {
  $stamp = (Get-Date).ToString('yyyyMMdd-HHmmssfff')
  & $tool --out (Join-Path $out ("render-$stamp-$n.json"))
  $n++
  Start-Sleep -Seconds $IntervalSeconds
}

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$inventory = Join-Path $PSScriptRoot 'scut-render-inventory.exe'
$probe = Join-Path $PSScriptRoot 'probe-headphones-phone-link.ps1'
$deadline = (Get-Date).AddSeconds(75)
while ((Get-Date) -lt $deadline) {
  $snapshot = (& $inventory | ConvertFrom-Json)
  $sentinel = @($snapshot.endpoints | ForEach-Object sessions | Where-Object { $_.sessionState -eq 'ACTIVE' -and $_.displayName -like '*Redmi Note 13 Pro+ 5G Hands-Free HF Audio*' })
  if ($sentinel.Count) { & $probe; exit $LASTEXITCODE }
  Start-Sleep -Seconds 1
}
exit 4

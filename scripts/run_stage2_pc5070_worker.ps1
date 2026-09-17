param(
    [Parameter(Mandatory = $true)][string]$RepositoryRoot,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$StatusPath,
    [Parameter(Mandatory = $true)][string]$StdoutPath,
    [Parameter(Mandatory = $true)][string]$StderrPath
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$started = [DateTime]::UtcNow.ToString('o')
$command = "`"$PythonExe`" scripts/run_e5_stage2.py --device cuda --batch-size 8 --output-dir output/scut_semantic_brain_v2_pc5070 --report-dir reports/scut_semantic_brain_v2_pc5070"

function Write-Status([string]$State, [Nullable[int]]$ExitCode = $null, [string]$ErrorMessage = $null) {
    $status = [ordered]@{
        state = $State; pid = $PID; start_time_utc = $started; end_time_utc = if ($State -in 'COMPLETED','FAILED') { [DateTime]::UtcNow.ToString('o') } else { $null }
        exit_code = $ExitCode; command = $command; stdout_log = $StdoutPath; stderr_log = $StderrPath; error = $ErrorMessage
    }
    $status | ConvertTo-Json | Set-Content -Encoding UTF8 $StatusPath
}

try {
    Write-Status 'PREPARING'
    Set-Location $RepositoryRoot
    Write-Status 'RUNNING'
    Add-Content -LiteralPath $StdoutPath -Value ("Worker cwd: " + (Get-Location).Path)
    Add-Content -LiteralPath $StdoutPath -Value ("Python: " + $PythonExe)
    & $PythonExe scripts/run_e5_stage2.py --device cuda --batch-size 8 --output-dir output/scut_semantic_brain_v2_pc5070 --report-dir reports/scut_semantic_brain_v2_pc5070 2>&1 | Tee-Object -FilePath $StdoutPath -Append
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) { Write-Status 'COMPLETED' $exitCode } else { Write-Status 'FAILED' $exitCode "Stage-2 runner exited with code $exitCode." }
    exit $exitCode
} catch {
    Write-Status 'FAILED' 1 $_.Exception.Message
    throw
}

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$DirectoryRows = if ($env:FILEZALL_PERF_DIRECTORY_ROWS) { $env:FILEZALL_PERF_DIRECTORY_ROWS } else { "5000" }
$TransferRows = if ($env:FILEZALL_PERF_TRANSFER_ROWS) { $env:FILEZALL_PERF_TRANSFER_ROWS } else { "2000" }
$ResourceSamples = if ($env:FILEZALL_PERF_RESOURCE_SAMPLES) { $env:FILEZALL_PERF_RESOURCE_SAMPLES } else { "120" }
$LogRows = if ($env:FILEZALL_PERF_LOG_ROWS) { $env:FILEZALL_PERF_LOG_ROWS } else { "5000" }
$RemoteRows = if ($env:FILEZALL_PERF_REMOTE_ROWS) { $env:FILEZALL_PERF_REMOTE_ROWS } else { "2000" }
$RemoteSamples = if ($env:FILEZALL_PERF_REMOTE_SAMPLES) { $env:FILEZALL_PERF_REMOTE_SAMPLES } else { "50" }
$HeartbeatSamples = if ($env:FILEZALL_PERF_HEARTBEAT_SAMPLES) { $env:FILEZALL_PERF_HEARTBEAT_SAMPLES } else { "50" }
$Output = if ($env:FILEZALL_PERF_OUTPUT) { $env:FILEZALL_PERF_OUTPUT } else { Join-Path $RepoRoot "performance-smoke.json" }
$Baseline = $env:FILEZALL_PERF_BASELINE

Write-Host "Running FileZall performance smoke"
Write-Host "Directory rows: $DirectoryRows"
Write-Host "Transfer rows: $TransferRows"
Write-Host "Resource samples: $ResourceSamples"
Write-Host "Log rows: $LogRows"
Write-Host "Remote rows: $RemoteRows"
Write-Host "Remote samples: $RemoteSamples"
Write-Host "Heartbeat samples: $HeartbeatSamples"
Write-Host "Output: $Output"
if ($Baseline) {
    Write-Host "Baseline: $Baseline"
}

$Args = @(
    "-m", "filezall_desktop.performance_smoke",
    "--directory-rows", $DirectoryRows,
    "--transfer-rows", $TransferRows,
    "--resource-samples", $ResourceSamples,
    "--log-rows", $LogRows,
    "--remote-rows", $RemoteRows,
    "--remote-samples", $RemoteSamples,
    "--heartbeat-samples", $HeartbeatSamples,
    "--output", $Output
)
if ($Baseline) {
    $Args += @("--baseline", $Baseline)
}

& $Python @Args

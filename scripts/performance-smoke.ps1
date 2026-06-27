$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$DirectoryRows = if ($env:FILEZALL_PERF_DIRECTORY_ROWS) { $env:FILEZALL_PERF_DIRECTORY_ROWS } else { "5000" }
$TransferRows = if ($env:FILEZALL_PERF_TRANSFER_ROWS) { $env:FILEZALL_PERF_TRANSFER_ROWS } else { "2000" }
$Output = if ($env:FILEZALL_PERF_OUTPUT) { $env:FILEZALL_PERF_OUTPUT } else { Join-Path $RepoRoot "performance-smoke.json" }

Write-Host "Running FileZall performance smoke"
Write-Host "Directory rows: $DirectoryRows"
Write-Host "Transfer rows: $TransferRows"
Write-Host "Output: $Output"

& $Python -m filezall_desktop.performance_smoke `
    --directory-rows $DirectoryRows `
    --transfer-rows $TransferRows `
    --output $Output

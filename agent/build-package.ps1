$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistDir = Join-Path $RepoRoot "dist"
$StageDir = Join-Path $DistDir "filezall-agent"

Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $StageDir | Out-Null
Copy-Item -Recurse -Path (Join-Path $RepoRoot "agent\filezall_agent") -Destination $StageDir
Copy-Item -Recurse -Path (Join-Path $RepoRoot "agent\systemd") -Destination $StageDir
Copy-Item -Recurse -Path (Join-Path $RepoRoot "agent\env") -Destination $StageDir

Push-Location $DistDir
try {
    tar -czf filezall-agent.tar.gz filezall-agent
} finally {
    Pop-Location
}

Write-Host "Created $DistDir\filezall-agent.tar.gz"

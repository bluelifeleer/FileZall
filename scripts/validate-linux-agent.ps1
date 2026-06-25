$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$HostName = $env:FILEZALL_LINUX_HOST
$UserName = $env:FILEZALL_LINUX_USER
$Token = $env:FILEZALL_LINUX_TOKEN
$Port = if ($env:FILEZALL_LINUX_PORT) { $env:FILEZALL_LINUX_PORT } else { "22" }
$SshKey = $env:FILEZALL_LINUX_SSH_KEY
$LocalPort = if ($env:FILEZALL_AGENT_LOCAL_PORT) { $env:FILEZALL_AGENT_LOCAL_PORT } else { "8765" }

foreach ($Required in @("FILEZALL_LINUX_HOST", "FILEZALL_LINUX_USER", "FILEZALL_LINUX_TOKEN")) {
    if (-not [Environment]::GetEnvironmentVariable($Required)) {
        throw "$Required is required for real Linux Agent validation."
    }
}

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "ssh is required."
}
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp is required."
}

$PackageScript = Join-Path $RepoRoot "agent\build-package.ps1"
$PackagePath = Join-Path $RepoRoot "dist\filezall-agent.tar.gz"

Write-Host "Building Agent package with agent\build-package.ps1"
& $PackageScript
if (-not (Test-Path -LiteralPath $PackagePath)) {
    throw "Agent package was not created at $PackagePath"
}

$Target = "$UserName@$HostName"
$SshBaseArgs = @()
$ScpBaseArgs = @()
if ($SshKey) {
    $SshBaseArgs += @("-i", $SshKey)
    $ScpBaseArgs += @("-i", $SshKey)
}
$SshBaseArgs += @("-p", $Port)
$ScpBaseArgs += @("-P", $Port)

Write-Host "Uploading Agent package with scp"
& scp @ScpBaseArgs $PackagePath "${Target}:/tmp/filezall-agent.tar.gz"

function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)

    Write-Host "ssh $Target $Command"
    & ssh @SshBaseArgs $Target $Command
}

$EscapedToken = $Token.Replace("'", "'\''")
$EnvCommand = "printf '%s\n' 'FILEZALL_AGENT_TOKEN=$EscapedToken' 'FILEZALL_AGENT_HOST=127.0.0.1' 'FILEZALL_AGENT_PORT=8765' | sudo tee /opt/filezall-agent/agent.env >/dev/null"

Invoke-Remote "sudo rm -rf /opt/filezall-agent"
Invoke-Remote "sudo mkdir -p /opt/filezall-agent"
Invoke-Remote "sudo tar -xzf /tmp/filezall-agent.tar.gz -C /opt/filezall-agent --strip-components=1"
Invoke-Remote $EnvCommand
Invoke-Remote "sudo cp /opt/filezall-agent/systemd/filezall-agent.service /etc/systemd/system/filezall-agent.service"
Invoke-Remote "sudo systemctl daemon-reload"
Invoke-Remote "sudo systemctl enable filezall-agent"
Invoke-Remote "sudo systemctl restart filezall-agent"
Invoke-Remote "systemctl is-active --quiet filezall-agent"

$Forward = "127.0.0.1:${LocalPort}:127.0.0.1:8765"
$TunnelArgs = @()
if ($SshKey) {
    $TunnelArgs += @("-i", $SshKey)
}
$TunnelArgs += @("-N", "-L", $Forward, "-p", $Port, $Target)

Write-Host "Opening ssh -L tunnel on 127.0.0.1:$LocalPort"
$Tunnel = Start-Process -FilePath "ssh" -ArgumentList $TunnelArgs -PassThru -WindowStyle Hidden
try {
    Start-Sleep -Seconds 2
    $Headers = @{ Authorization = "Bearer $Token" }
    $BaseUrl = "http://127.0.0.1:$LocalPort"

    Write-Host "Checking /health"
    $Health = Invoke-RestMethod -Uri "$BaseUrl/health" -Headers $Headers -TimeoutSec 10
    if (-not $Health.ok) {
        throw "Agent /health did not return ok=true."
    }

    Write-Host "Checking /resources"
    $Resources = Invoke-RestMethod -Uri "$BaseUrl/resources" -Headers $Headers -TimeoutSec 10
    if ($null -eq $Resources.cpu -or $null -eq $Resources.memory) {
        throw "Agent /resources response did not include cpu and memory."
    }

    Write-Host "Linux Agent end-to-end validation passed."
} finally {
    if ($Tunnel -and -not $Tunnel.HasExited) {
        Stop-Process -Id $Tunnel.Id -Force
    }
}

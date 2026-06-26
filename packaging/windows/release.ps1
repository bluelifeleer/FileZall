$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Version = if ($env:FILEZALL_VERSION) {
    $env:FILEZALL_VERSION
} else {
    $Toml = Get-Content (Join-Path $RepoRoot "pyproject.toml") -Raw
    if ($Toml -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
        throw "Could not read project.version from pyproject.toml"
    }
    $Matches[1]
}

Push-Location $RepoRoot
try {
    & (Join-Path $RepoRoot "packaging\windows\build.ps1")

    $PortableExe = Join-Path $RepoRoot "dist\FileZall\FileZall.exe"
    if ($env:FILEZALL_WINDOWS_SIGN -eq "1") {
        & (Join-Path $RepoRoot "packaging\windows\sign.ps1") -Path $PortableExe
    }

    $Installer = Join-Path $RepoRoot "dist\installer\FileZallSetup.exe"
    $VersionedInstaller = $null
    if (Test-Path -LiteralPath $Installer) {
        if ($env:FILEZALL_WINDOWS_SIGN -eq "1") {
            & (Join-Path $RepoRoot "packaging\windows\sign.ps1") -Path $Installer
        }
        $VersionedInstaller = Join-Path $RepoRoot "dist\FileZall-$Version-windows-x64-setup.exe"
        Copy-Item -LiteralPath $Installer -Destination $VersionedInstaller -Force
        Copy-Item -LiteralPath $Installer -Destination (Join-Path $RepoRoot "dist\FileZall-windows-x64-setup.exe") -Force
    }

    $PortableZip = Join-Path $RepoRoot "dist\FileZall-$Version-windows-x64-portable.zip"
    if (Test-Path -LiteralPath $PortableZip) {
        Remove-Item -LiteralPath $PortableZip -Force
    }
    Compress-Archive -Path (Join-Path $RepoRoot "dist\FileZall\*") -DestinationPath $PortableZip
    Copy-Item -LiteralPath $PortableZip -Destination (Join-Path $RepoRoot "dist\FileZall-windows-x64-portable.zip") -Force

    $ChecksumTargets = @($PortableZip)
    if ($VersionedInstaller -and (Test-Path -LiteralPath $VersionedInstaller)) {
        $ChecksumTargets += $VersionedInstaller
    }
    $ChecksumPath = Join-Path $RepoRoot "dist\FileZall-$Version-windows-SHA256SUMS.txt"
    $ChecksumTargets | ForEach-Object {
        $Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_
        "$($Hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $_)"
    } | Set-Content -Encoding ascii $ChecksumPath
    Copy-Item -LiteralPath $ChecksumPath -Destination (Join-Path $RepoRoot "dist\FileZall-windows-SHA256SUMS.txt") -Force

    if ($env:FILEZALL_WINDOWS_SIGN -eq "1") {
        foreach ($Target in $ChecksumTargets) {
            if ((Split-Path -Leaf $Target) -like "*.exe") {
                signtool verify /pa /v $Target
            }
        }
    }

    Write-Host "Release artifacts:"
    Write-Host "  $PortableZip"
    if ($VersionedInstaller -and (Test-Path -LiteralPath $VersionedInstaller)) {
        Write-Host "  $VersionedInstaller"
    }
    Write-Host "  $ChecksumPath"
} finally {
    Pop-Location
}

$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "pyinstaller is required. Install it in the build environment before running this script."
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$SpecPath = Join-Path $RepoRoot "packaging\filezall.spec"

Push-Location $RepoRoot
try {
    pyinstaller --clean --noconfirm $SpecPath

    if (Get-Command iscc -ErrorAction SilentlyContinue) {
        iscc (Join-Path $RepoRoot "packaging\windows\FileZall.iss")
    } else {
        Write-Warning "Inno Setup compiler 'iscc' was not found. The portable build is available under dist\FileZall."
    }
} finally {
    Pop-Location
}

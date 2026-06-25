$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$SpecPath = Join-Path $RepoRoot "packaging\filezall.spec"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPython) {
    $PythonExe = $VenvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = (Get-Command python).Source
} else {
    throw "Python is required. Create .venv or add python to PATH before running this script."
}

& $PythonExe -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required in the build Python. Run: $PythonExe -m pip install pyinstaller"
}

Push-Location $RepoRoot
try {
    & $PythonExe -m PyInstaller --clean --noconfirm $SpecPath

    if (Get-Command iscc -ErrorAction SilentlyContinue) {
        iscc (Join-Path $RepoRoot "packaging\windows\FileZall.iss")
    } else {
        Write-Warning "Inno Setup compiler 'iscc' was not found. The portable build is available under dist\FileZall."
    }
} finally {
    Pop-Location
}

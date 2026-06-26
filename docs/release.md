# FileZall Release Guide

This guide covers production release packaging for macOS and Windows.

## Release Checklist

1. Update versions in `pyproject.toml` and `src/filezall_core/__init__.py`.
2. Run the test suite on the target platform.
3. Build platform artifacts from a clean checkout.
4. Sign platform binaries and installers.
5. Notarize macOS artifacts.
6. Generate SHA256 checksums.
7. Smoke test install and launch on a clean machine or VM.
8. Publish the versioned artifacts and checksums.

## macOS

Prerequisites:

- macOS build host.
- Python 3.11 or newer with project dependencies and PyInstaller installed.
- Xcode Command Line Tools.
- Apple Developer Program membership for production signing.
- Developer ID Application certificate installed in the login keychain.
- App Store Connect API key for notarization.

Unsigned local release artifact:

```bash
bash packaging/macos/release.sh
```

Signed and notarized production artifact:

```bash
export FILEZALL_MACOS_CODESIGN_IDENTITY="Developer ID Application: Example Inc. (TEAMID)"
export FILEZALL_MACOS_NOTARIZE=1
export APP_STORE_CONNECT_KEY="/secure/path/AuthKey_ABC123DEFG.p8"
export APP_STORE_CONNECT_KEY_ID="ABC123DEFG"
export APP_STORE_CONNECT_ISSUER_ID="00000000-0000-0000-0000-000000000000"

bash packaging/macos/release.sh
```

Outputs:

- `dist/FileZall-<version>-macos-arm64.zip`
- `dist/FileZall-<version>-macos-arm64.dmg`
- `dist/FileZall-<version>-macos-SHA256SUMS.txt`

Validation commands:

```bash
codesign --verify --deep --strict --verbose=2 dist/FileZall.app
spctl --assess --type execute --verbose dist/FileZall.app
hdiutil verify dist/FileZall-<version>-macos-arm64.dmg
```

## Windows

Prerequisites:

- Windows build host.
- Python 3.11 or newer with project dependencies and PyInstaller installed.
- Inno Setup on `PATH` as `iscc` for setup installer output.
- Windows SDK on `PATH` as `signtool` for production signing.
- Authenticode code signing certificate.

Unsigned local release artifact:

```powershell
packaging\windows\release.ps1
```

Signed production artifact with a PFX certificate:

```powershell
$env:FILEZALL_WINDOWS_SIGN = "1"
$env:FILEZALL_WINDOWS_CERT_PATH = "C:\secure\filezall-code-signing.pfx"
$env:FILEZALL_WINDOWS_CERT_PASSWORD = "<password>"
$env:FILEZALL_WINDOWS_TIMESTAMP_URL = "http://timestamp.digicert.com"

packaging\windows\release.ps1
```

If the certificate is installed in the Windows certificate store, omit
`FILEZALL_WINDOWS_CERT_PATH` and `FILEZALL_WINDOWS_CERT_PASSWORD`; `signtool /a`
will select a suitable code signing certificate.

Outputs:

- `dist/FileZall-<version>-windows-x64-setup.exe` when Inno Setup is available.
- `dist/FileZall-<version>-windows-x64-portable.zip`
- `dist/FileZall-<version>-windows-SHA256SUMS.txt`

Validation commands:

```powershell
signtool verify /pa /v dist\FileZall-<version>-windows-x64-setup.exe
Get-FileHash -Algorithm SHA256 dist\FileZall-<version>-windows-x64-setup.exe
```

## Notes

- Keep signing certificates and notarization keys outside the repository.
- Prefer tag-triggered CI releases, for example `v0.1.0`.
- Windows SmartScreen reputation accrues over time; EV signing usually reduces early warnings more than OV signing.
- Notarization is only for macOS distribution. Local development builds do not need it.

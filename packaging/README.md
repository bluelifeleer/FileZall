# FileZall Packaging

This folder contains the release scaffolding for Windows and macOS desktop builds.

## Windows

Run from PowerShell on a Windows build machine:

```powershell
packaging\windows\build.ps1
```

The script runs `pyinstaller` with `packaging/filezall.spec`. If Inno Setup is installed and `iscc` is on `PATH`, it also builds `dist/installer/FileZallSetup.exe`.

## macOS

Run on a macOS build machine:

```bash
bash packaging/macos/build.sh
```

The script runs `pyinstaller` and uses `create-dmg` when available.

For versioned release artifacts, signing, notarization, and checksums, run:

```bash
bash packaging/macos/release.sh
```

Set `FILEZALL_MACOS_CODESIGN_IDENTITY` and `FILEZALL_MACOS_NOTARIZE=1` for a
production Developer ID notarized release.

## Release Automation

See `docs/release.md` for the full macOS and Windows signing, notarization,
checksum, and publication workflow.

## Release Notes

Production distribution still needs platform code signing. Windows builds should be signed with an Authenticode certificate. macOS builds require code signing and notarization before public distribution.

## Linux Agent

Build and deployment notes for the optional Linux Agent are in `docs/agent-deployment.md`.

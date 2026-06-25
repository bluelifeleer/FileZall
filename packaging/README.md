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

## Release Notes

Production distribution still needs platform code signing. Windows builds should be signed with an Authenticode certificate. macOS builds require code signing and notarization before public distribution.

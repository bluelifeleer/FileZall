# FileZall M10 Release Verification Design

## Goal

Implement a practical release-verification path for FileZall: build a real Windows executable on this machine and provide a repeatable Linux Agent end-to-end validation script for a real server.

## Windows Build Design

The Windows build should work from the repository root and prefer the project virtual environment. `packaging/windows/build.ps1` will look for `.venv\Scripts\python.exe`, verify that `PyInstaller` is importable, and run `python -m PyInstaller` against `packaging/filezall.spec`. This avoids relying on a global `pyinstaller` command.

If Inno Setup is installed, the script will run `iscc` and produce `dist/installer/FileZallSetup.exe`. If it is not installed, the script will keep the portable build under `dist\FileZall` and print a clear warning rather than failing the whole release build.

The Inno Setup script must use a valid GUID-style `AppId`, because the current installer metadata is part of the real build contract.

## Linux Agent Validation Design

Add `scripts/validate-linux-agent.ps1` as the real-server verification entry point. It will require:

- `FILEZALL_LINUX_HOST`
- `FILEZALL_LINUX_USER`
- `FILEZALL_LINUX_TOKEN`

It will support optional:

- `FILEZALL_LINUX_PORT`
- `FILEZALL_LINUX_SSH_KEY`
- `FILEZALL_AGENT_LOCAL_PORT`

The script will build `dist/filezall-agent.tar.gz`, upload it with `scp`, install/update the Agent over `ssh`, start the `filezall-agent` systemd service, open an `ssh -L` tunnel, call `/health`, and call `/resources`. The script should fail clearly when required environment variables are missing.

## Testing

Automated tests will check script contents and installer metadata. Real Windows packaging will be verified by actually running the build script after installing PyInstaller into the virtual environment if needed. Real Linux verification will run only when server environment variables are present; otherwise, the script remains ready and self-validating but cannot complete against a real host.

## Out Of Scope

This step does not install Inno Setup automatically, perform code signing, notarize macOS builds, or invent Linux server credentials. It also does not expose the Agent publicly; SSH tunneling remains the supported verification path.
